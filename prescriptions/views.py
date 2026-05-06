import logging
import os
import tempfile

from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins, parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.choices import (
    PrescriptionAccessTypeChoices,
    PrescriptionStatusChoices,
    RoleChoices,
    SignStatusChoices,
    TranscriptionStatusChoices,
)
from common.permissions import (
    CanManagePatients,
    IsApprovedPharmacistRole,
    IsPharmacistRole,
    IsPatientRole,
    has_patient_management_access,
)

from .constants import DOCTOR_SPECIALTY_OPTIONS
from .models import Prescription, PrescriptionItem
from .serializers import (
    ApproveTranscriptSerializer,
    PharmacistPrescriptionCreateSerializer,
    PharmacistPrescriptionItemAudioTranscriptionSerializer,
    PharmacistPrescriptionItemInputSerializer,
    PharmacistPrescriptionItemSerializer,
    PharmacistPrescriptionListSerializer,
    PharmacistPrescriptionSerializer,
    PharmacistPrescriptionSubmitSerializer,
    PharmacistPrescriptionUpdateSerializer,
    PrescriptionConfirmSerializer,
    PrescriptionCreateSerializer,
    PrescriptionItemCreateSerializer,
    PrescriptionItemSerializer,
    PrescriptionItemTranscriptionRequestSerializer,
    PrescriptionItemUpdateSerializer,
    PrescriptionSerializer,
)
from .services import (
    SignGenerationError,
    generate_sign_gloss,
    log_prescription_access,
    mark_prescription_item_sign_completed,
    mark_prescription_item_sign_failed,
    mark_prescription_item_sign_processing,
    transcribe_prescription_item,
)
from transcriptions.exceptions import AudioTranscriptionError
from transcriptions.services import transcribe_audio_file

logger = logging.getLogger(__name__)


def ensure_draft_prescription(prescription):
    if prescription.status != PrescriptionStatusChoices.DRAFT:
        raise ValidationError({"detail": "Only draft prescriptions can be modified."})


def ensure_sign_generation_prescription(prescription):
    if prescription.status not in {
        PrescriptionStatusChoices.DRAFT,
        PrescriptionStatusChoices.SUBMITTED,
    }:
        raise ValidationError(
            {
                "detail": "Only draft or submitted prescriptions can generate sign output."
            }
        )


PRESCRIPTION_STATUS_TRANSITIONS = {
    PrescriptionStatusChoices.DRAFT: {PrescriptionStatusChoices.SUBMITTED},
    PrescriptionStatusChoices.SUBMITTED: {
        PrescriptionStatusChoices.CONFIRMED,
        PrescriptionStatusChoices.CANCELLED,
    },
    PrescriptionStatusChoices.CONFIRMED: {
        PrescriptionStatusChoices.DELIVERED,
        PrescriptionStatusChoices.CANCELLED,
    },
    PrescriptionStatusChoices.DELIVERED: {PrescriptionStatusChoices.ARCHIVED},
    PrescriptionStatusChoices.CANCELLED: {PrescriptionStatusChoices.ARCHIVED},
    PrescriptionStatusChoices.ARCHIVED: set(),
}


def prescription_error(
    detail, code, *, status_code=status.HTTP_400_BAD_REQUEST, **extra
):
    payload = {"detail": detail, "code": code}
    payload.update(extra)
    return Response(payload, status=status_code)


def serializer_error_response(serializer):
    def first_value(value):
        if isinstance(value, (list, tuple)) and value:
            return first_value(value[0])
        return str(value)

    errors = serializer.errors
    if isinstance(errors, dict):
        detail = errors.get("detail")
        code = errors.get("code")
        if detail and code:
            return prescription_error(first_value(detail), first_value(code))
        non_field_errors = errors.get("non_field_errors")
        if non_field_errors:
            first = non_field_errors[0]
            if isinstance(first, dict) and first.get("detail") and first.get("code"):
                return prescription_error(
                    first_value(first["detail"]),
                    first_value(first["code"]),
                )
        for value in errors.values():
            if isinstance(value, dict) and value.get("detail") and value.get("code"):
                return prescription_error(
                    first_value(value["detail"]),
                    first_value(value["code"]),
                )
    return Response(errors, status=status.HTTP_400_BAD_REQUEST)


def media_url(request, file_field):
    if not file_field:
        return None
    try:
        url = file_field.url
    except ValueError:
        return None
    return request.build_absolute_uri(url) if request else url


def invalid_prescription_transition_response(current_status, target_status):
    return prescription_error(
        f"Cannot move prescription from {current_status} to {target_status}",
        "invalid_prescription_status_transition",
        current_status=current_status,
        target_status=target_status,
    )


class PrescriptionViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]
    queryset = Prescription.objects.select_related(
        "patient",
        "patient__user",
        "patient__organization",
        "pharmacist",
        "pharmacist__user",
        "pharmacy",
    ).prefetch_related("items", "patient__medical_info")
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return PrescriptionCreateSerializer
        if self.action == "add_item":
            return PrescriptionItemCreateSerializer
        if self.action == "confirm":
            return PrescriptionConfirmSerializer
        return PrescriptionSerializer

    def get_permissions(self):
        if self.action in {"create", "add_item", "confirm"}:
            permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]
        elif (
            self.request.user.is_authenticated
            and self.request.user.role == RoleChoices.ADMIN
        ):
            permission_classes = [IsAuthenticated, CanManagePatients]
        elif (
            self.request.user.is_authenticated
            and self.request.user.role == RoleChoices.PATIENT
        ):
            permission_classes = [IsAuthenticated, IsPatientRole]
        else:
            permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.role == RoleChoices.ADMIN:
            if not has_patient_management_access(user):
                return queryset.none()
            staff_profile = getattr(user, "organization_staff_profile", None)
            if staff_profile is None:
                return queryset
            return queryset.filter(patient__organization=staff_profile.organization)
        if user.role == RoleChoices.PHARMACIST:
            pharmacist_profile = getattr(user, "pharmacist_profile", None)
            if pharmacist_profile is None:
                return queryset.none()
            return queryset.filter(pharmacist=pharmacist_profile)
        if user.role == RoleChoices.PATIENT:
            patient_profile = getattr(user, "patient_profile", None)
            if patient_profile is None:
                return queryset.none()
            return queryset.filter(patient=patient_profile)
        return queryset.none()

    def create(self, request, *args, **kwargs):
        return Response(
            {
                "detail": (
                    "Use /api/pharmacist/prescriptions/ with a valid active patient "
                    "session to create prescriptions."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def retrieve(self, request, *args, **kwargs):
        prescription = self.get_object()
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.VIEW,
        )
        serializer = self.get_serializer(prescription)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="items")
    def add_item(self, request, pk=None):
        prescription = self.get_object()
        if prescription.pharmacist.user_id != request.user.id:
            raise PermissionDenied("Only the prescription pharmacist can add items.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(prescription=prescription)
        return Response(
            PrescriptionItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        prescription = self.get_object()
        if prescription.pharmacist.user_id != request.user.id:
            return prescription_error(
                "Only the prescription pharmacist can confirm it.",
                "prescription_permission_denied",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        if prescription.status not in {
            PrescriptionStatusChoices.DRAFT,
            PrescriptionStatusChoices.SUBMITTED,
        }:
            return invalid_prescription_transition_response(
                prescription.status,
                PrescriptionStatusChoices.CONFIRMED,
            )
        prescription.status = PrescriptionStatusChoices.CONFIRMED
        prescription.save(update_fields=["status", "updated_at"])
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.CONFIRM,
        )
        return Response(
            {
                "detail": "Prescription confirmed successfully",
                "prescription": PrescriptionSerializer(
                    prescription,
                    context={"request": request},
                ).data,
            }
        )


class PrescriptionItemViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = PrescriptionItemUpdateSerializer
    permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]
    queryset = PrescriptionItem.objects.select_related(
        "prescription", "prescription__pharmacist"
    )
    http_method_names = ["patch", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "transcribe":
            return PrescriptionItemTranscriptionRequestSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        pharmacist_profile = getattr(self.request.user, "pharmacist_profile", None)
        if pharmacist_profile is None:
            return super().get_queryset().none()
        return (
            super().get_queryset().filter(prescription__pharmacist=pharmacist_profile)
        )

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        log_prescription_access(
            self.get_object().prescription,
            request.user,
            PrescriptionAccessTypeChoices.ITEM_UPDATE,
        )
        return response

    @action(detail=True, methods=["post"], url_path="transcribe")
    def transcribe(self, request, pk=None):
        item = self.get_object()
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            item = transcribe_prescription_item(
                item,
                requested_by=request.user,
                force=serializer.validated_data["force"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(PrescriptionItemSerializer(item).data)


class PharmacistPrescriptionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPharmacistRole]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def _get_pharmacist(self):
        return self.request.user.pharmacist_profile

    def _ensure_approved(self):
        if not self._get_pharmacist().is_approved:
            raise PermissionDenied("Pharmacist account is not approved.")

    def _queryset(self):
        queryset = (
            Prescription.objects.select_related(
                "patient",
                "patient__user",
                "pharmacist",
                "pharmacy",
                "session",
            )
            .prefetch_related("items")
            .filter(pharmacist=self._get_pharmacist())
        )
        status_filter = self.request.query_params.get("status")
        patient_id = self.request.query_params.get("patient_id")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset

    def _get_prescription(self, prescription_id):
        return self._queryset().get(pk=prescription_id)

    def _not_found_response(self):
        return prescription_error(
            "Prescription not found",
            "prescription_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    def _item_not_found_response(self):
        return prescription_error(
            "Item not found",
            "item_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    def _ensure_not_archived(self, prescription):
        if prescription.status == PrescriptionStatusChoices.ARCHIVED:
            return prescription_error(
                "Prescription is archived",
                "prescription_archived",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def _ensure_draft_response(self, prescription):
        archived_response = self._ensure_not_archived(prescription)
        if archived_response is not None:
            return archived_response
        if prescription.status != PrescriptionStatusChoices.DRAFT:
            return prescription_error(
                "Only draft prescriptions can be modified.",
                "invalid_prescription_status",
            )
        return None

    def _ensure_sign_generation_response(self, prescription):
        archived_response = self._ensure_not_archived(prescription)
        if archived_response is not None:
            return archived_response
        if prescription.status not in {
            PrescriptionStatusChoices.DRAFT,
            PrescriptionStatusChoices.SUBMITTED,
        }:
            return prescription_error(
                "Only draft or submitted prescriptions can generate sign output.",
                "invalid_prescription_status",
            )
        return None

    def _lifecycle_response(self, detail, prescription):
        prescription.refresh_from_db()
        return Response(
            {
                "detail": detail,
                "prescription": PharmacistPrescriptionSerializer(
                    prescription,
                    context={"request": self.request},
                ).data,
            }
        )

    def _transition_prescription(self, prescription, target_status, detail):
        allowed_targets = PRESCRIPTION_STATUS_TRANSITIONS.get(
            prescription.status, set()
        )
        if target_status not in allowed_targets:
            return invalid_prescription_transition_response(
                prescription.status,
                target_status,
            )
        update_fields = ["status", "updated_at"]
        prescription.status = target_status
        now = timezone.now()
        if target_status == PrescriptionStatusChoices.SUBMITTED:
            prescription.submitted_at = now
            update_fields.append("submitted_at")
        if target_status == PrescriptionStatusChoices.DELIVERED:
            prescription.delivered_at = now
            update_fields.append("delivered_at")
        prescription.save(update_fields=update_fields)
        return self._lifecycle_response(detail, prescription)

    def list(self, request):
        queryset = self._queryset().annotate(item_count=Count("items"))
        serializer = PharmacistPrescriptionListSerializer(
            queryset,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    def doctor_specialties(self, request):
        return Response({"results": DOCTOR_SPECIALTY_OPTIONS})

    def create(self, request):
        self._ensure_approved()
        serializer = PharmacistPrescriptionCreateSerializer(
            data=request.data,
            context={"request": request, "now": timezone.now},
        )
        serializer.is_valid(raise_exception=True)
        prescription = serializer.save()
        return Response(
            PharmacistPrescriptionSerializer(
                prescription,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, prescription_id):
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.VIEW,
        )
        return Response(
            PharmacistPrescriptionSerializer(
                prescription,
                context={"request": request},
            ).data
        )

    def partial_update(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        blocked = self._ensure_draft_response(prescription)
        if blocked is not None:
            return blocked
        serializer = PharmacistPrescriptionUpdateSerializer(
            prescription,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            PharmacistPrescriptionSerializer(
                prescription,
                context={"request": request},
            ).data
        )

    def add_item(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        blocked = self._ensure_draft_response(prescription)
        if blocked is not None:
            return blocked
        serializer = PharmacistPrescriptionItemInputSerializer(data=request.data)
        if not serializer.is_valid():
            return serializer_error_response(serializer)
        item = PrescriptionItem.objects.create(
            prescription=prescription,
            **serializer.validated_data,
        )
        return Response(
            PharmacistPrescriptionItemSerializer(
                item,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def update_item(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        blocked = self._ensure_draft_response(prescription)
        if blocked is not None:
            return blocked
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return self._item_not_found_response()
        serializer = PharmacistPrescriptionItemInputSerializer(
            item,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return serializer_error_response(serializer)
        for field, value in serializer.validated_data.items():
            setattr(item, field, value)
        item.save()
        return Response(
            PharmacistPrescriptionItemSerializer(
                item,
                context={"request": request},
            ).data
        )

    def delete_item(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        blocked = self._ensure_draft_response(prescription)
        if blocked is not None:
            return blocked
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return self._item_not_found_response()
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def transcribe_audio(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        blocked = self._ensure_draft_response(prescription)
        if blocked is not None:
            return blocked
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return self._item_not_found_response()

        serializer = PharmacistPrescriptionItemAudioTranscriptionSerializer(
            data=request.data
        )
        if not serializer.is_valid():
            return serializer_error_response(serializer)

        now = timezone.now()
        audio_file = serializer.validated_data["audio"]
        item.instructions_audio.save(
            getattr(audio_file, "name", "") or "instructions.audio",
            audio_file,
            save=False,
        )
        item.transcription_status = TranscriptionStatusChoices.PROCESSING
        item.transcription_requested_at = now
        item.transcription_error_message = ""
        item.instructions_text = ""
        item.instructions_transcript_raw = ""
        item.instructions_transcript_edited = ""
        item.save(
            update_fields=[
                "instructions_audio",
                "transcription_status",
                "transcription_requested_at",
                "transcription_error_message",
                "instructions_text",
                "instructions_transcript_raw",
                "instructions_transcript_edited",
                "updated_at",
            ]
        )
        item.refresh_from_db()
        if hasattr(audio_file, "seek"):
            audio_file.seek(0)

        if not settings.GEMINI_API_KEY:
            failed_at = timezone.now()
            PrescriptionItem.objects.filter(pk=item.pk).update(
                transcription_status=TranscriptionStatusChoices.FAILED,
                transcription_provider="gemini",
                transcription_completed_at=failed_at,
                transcription_error_message="Audio transcription provider is not configured",
                updated_at=failed_at,
            )
            item.refresh_from_db()
            return Response(
                {
                    "detail": "Audio transcription provider is not configured",
                    "code": "transcription_provider_not_configured",
                    "item_id": item.id,
                    "transcription_status": item.transcription_status,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        temp_path = None
        try:
            suffix = (
                getattr(audio_file, "name", "") and os.path.splitext(audio_file.name)[1]
            ) or ".audio"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = temp_file.name
                for chunk in audio_file.chunks():
                    temp_file.write(chunk)
            result = transcribe_audio_file(
                temp_path,
                mime_type=(getattr(audio_file, "content_type", None) or None),
            )
            transcript = result["transcript"]
        except AudioTranscriptionError as exc:
            if settings.DEBUG:
                logger.exception("Audio transcription provider failed.")
            provider_error = exc.safe_message
            failed_at = timezone.now()
            PrescriptionItem.objects.filter(pk=item.pk).update(
                transcription_status=TranscriptionStatusChoices.FAILED,
                transcription_provider="gemini",
                transcription_completed_at=failed_at,
                transcription_error_message=provider_error,
                updated_at=failed_at,
            )
            item.refresh_from_db()
            return Response(
                {
                    "detail": "Audio transcription failed",
                    "code": "transcription_failed",
                    "item_id": item.id,
                    "transcription_status": item.transcription_status,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        completed_at = timezone.now()
        PrescriptionItem.objects.filter(pk=item.pk).update(
            instructions_transcript_raw=transcript,
            transcription_status=TranscriptionStatusChoices.COMPLETED,
            transcription_provider=result["provider"],
            transcription_completed_at=completed_at,
            transcription_error_message="",
            updated_at=completed_at,
        )
        item.refresh_from_db()
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.TRANSCRIBE,
        )
        return Response(
            {
                "item_id": item.id,
                "transcription_status": item.transcription_status,
                "raw_transcript": item.instructions_transcript_raw,
                "approved_instruction_text": None,
                "provider": result["provider"],
                "model": result["model"],
                "audio_url": media_url(request, item.instructions_audio),
                "detail": "Audio transcribed successfully",
            }
        )

    def approve_transcript(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        blocked = self._ensure_draft_response(prescription)
        if blocked is not None:
            return blocked
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return self._item_not_found_response()

        serializer = ApproveTranscriptSerializer(data=request.data)
        if not serializer.is_valid():
            return serializer_error_response(serializer)
        approved_text = serializer.validated_data["approved_instruction_text"]
        item.instructions_transcript_edited = approved_text
        item.transcription_status = TranscriptionStatusChoices.COMPLETED
        item.save(
            update_fields=[
                "instructions_transcript_edited",
                "transcription_status",
                "updated_at",
            ]
        )
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.ITEM_UPDATE,
        )
        return Response(
            {
                "item_id": item.id,
                "raw_transcript": item.instructions_transcript_raw,
                "approved_instruction_text": item.instructions_transcript_edited,
                "transcription_status": "approved",
                "detail": "Transcript approved successfully",
            }
        )

    def generate_sign(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        blocked = self._ensure_sign_generation_response(prescription)
        if blocked is not None:
            return blocked
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return self._item_not_found_response()

        source_text = (
            item.instructions_transcript_edited.strip()
            or item.instructions_transcript_raw.strip()
            or item.instructions_text.strip()
        )
        if not source_text:
            return Response(
                {
                    "detail": "No instruction text is available for gloss generation.",
                    "code": "missing_instruction_text",
                    "item_id": item.id,
                    "sign_status": item.sign_status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not settings.GEMINI_API_KEY:
            mark_prescription_item_sign_failed(item)
            item.refresh_from_db()
            return Response(
                {
                    "detail": "Gloss generation provider is not configured",
                    "code": "gloss_provider_not_configured",
                    "item_id": item.id,
                    "sign_status": item.sign_status,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        mark_prescription_item_sign_processing(item)
        item.refresh_from_db()
        try:
            result = generate_sign_gloss(source_text)
        except SignGenerationError:
            if settings.DEBUG:
                logger.exception("Sign/gloss generation provider failed.")
            mark_prescription_item_sign_failed(item)
            item.refresh_from_db()
            return Response(
                {
                    "detail": "Gloss generation failed",
                    "code": "gloss_generation_failed",
                    "item_id": item.id,
                    "sign_status": item.sign_status,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        mark_prescription_item_sign_completed(item, result["gloss_text"])
        item.refresh_from_db()
        return Response(
            {
                "item_id": item.id,
                "sign_status": SignStatusChoices.COMPLETED,
                "gloss_text": item.supporting_text,
                "supporting_text": item.supporting_text,
                "video_url": None,
                "output_type": "gloss_only",
                "video_generation_supported": False,
                "detail": "Gloss generated successfully",
            }
        )

    def submit(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        serializer = PharmacistPrescriptionSubmitSerializer(
            data=request.data or {},
            context={"prescription": prescription},
        )
        if not serializer.is_valid():
            return prescription_error(
                "Prescription must include at least one item before submission",
                "prescription_has_no_items",
            )
        return self._transition_prescription(
            prescription,
            PrescriptionStatusChoices.SUBMITTED,
            "Prescription submitted successfully",
        )

    def confirm(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        response = self._transition_prescription(
            prescription,
            PrescriptionStatusChoices.CONFIRMED,
            "Prescription confirmed successfully",
        )
        if response.status_code == status.HTTP_200_OK:
            log_prescription_access(
                prescription,
                request.user,
                PrescriptionAccessTypeChoices.CONFIRM,
            )
        return response

    def deliver(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        return self._transition_prescription(
            prescription,
            PrescriptionStatusChoices.DELIVERED,
            "Prescription delivered successfully",
        )

    def cancel(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        return self._transition_prescription(
            prescription,
            PrescriptionStatusChoices.CANCELLED,
            "Prescription cancelled successfully",
        )

    def archive(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return self._not_found_response()
        return self._transition_prescription(
            prescription,
            PrescriptionStatusChoices.ARCHIVED,
            "Prescription archived successfully",
        )


class PatientPrescriptionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAuthenticated, IsPatientRole]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        patient_profile = getattr(self.request.user, "patient_profile", None)
        if patient_profile is None:
            return Prescription.objects.none()
        queryset = (
            Prescription.objects.select_related(
                "pharmacist",
                "pharmacist__user",
                "pharmacy",
                "patient",
                "patient__user",
            )
            .prefetch_related("items")
            .filter(patient=patient_profile)
        )
        include_drafts = self.request.query_params.get("include_drafts") == "true"
        if not include_drafts:
            queryset = queryset.exclude(status=PrescriptionStatusChoices.DRAFT)
        return queryset

    def retrieve(self, request, *args, **kwargs):
        prescription = self.get_object()
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.VIEW,
        )
        serializer = self.get_serializer(prescription)
        return Response(serializer.data)
