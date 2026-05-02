import logging

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
)
from common.permissions import (
    CanManagePatients,
    IsApprovedPharmacistRole,
    IsPharmacistRole,
    IsPatientRole,
    has_patient_management_access,
    pharmacist_can_access_patient,
)

from .models import Prescription, PrescriptionItem
from .serializers import (
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
    TranscribedPrescriptionItemSerializer,
)
from .services import log_prescription_access, transcribe_prescription_item
from transcriptions.exceptions import AudioTranscriptionError
from transcriptions.services import (
    get_transcription_provider_name,
    transcribe_audio_file,
)

logger = logging.getLogger(__name__)


def ensure_draft_prescription(prescription):
    if prescription.status != PrescriptionStatusChoices.DRAFT:
        raise ValidationError({"detail": "Only draft prescriptions can be modified."})


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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = serializer.validated_data["patient"]
        if not pharmacist_can_access_patient(request.user, patient):
            raise PermissionDenied("You do not have workflow access to this patient.")
        pharmacist_profile = request.user.pharmacist_profile
        prescription = serializer.save(
            pharmacist=pharmacist_profile,
            pharmacy=pharmacist_profile.pharmacy,
            status=PrescriptionStatusChoices.DRAFT,
        )
        return Response(
            PrescriptionSerializer(
                prescription, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
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
            raise PermissionDenied("Only the prescription pharmacist can confirm it.")
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        prescription.status = PrescriptionStatusChoices.CONFIRMED
        prescription.save(update_fields=["status", "updated_at"])
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.CONFIRM,
        )
        return Response(PrescriptionSerializer(prescription).data)


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

    def list(self, request):
        queryset = self._queryset().annotate(item_count=Count("items"))
        serializer = PharmacistPrescriptionListSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request):
        self._ensure_approved()
        serializer = PharmacistPrescriptionCreateSerializer(
            data=request.data,
            context={"request": request, "now": timezone.now},
        )
        serializer.is_valid(raise_exception=True)
        prescription = serializer.save()
        return Response(
            PharmacistPrescriptionSerializer(prescription).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, prescription_id):
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.VIEW,
        )
        return Response(PharmacistPrescriptionSerializer(prescription).data)

    def partial_update(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ensure_draft_prescription(prescription)
        serializer = PharmacistPrescriptionUpdateSerializer(
            prescription,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PharmacistPrescriptionSerializer(prescription).data)

    def add_item(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ensure_draft_prescription(prescription)
        serializer = PharmacistPrescriptionItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = PrescriptionItem.objects.create(
            prescription=prescription,
            **serializer.validated_data,
        )
        return Response(
            PharmacistPrescriptionItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )

    def update_item(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ensure_draft_prescription(prescription)
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PharmacistPrescriptionItemInputSerializer(
            item,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(item, field, value)
        item.save()
        return Response(PharmacistPrescriptionItemSerializer(item).data)

    def delete_item(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ensure_draft_prescription(prescription)
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def transcribe_audio(self, request, prescription_id, item_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ensure_draft_prescription(prescription)
        try:
            item = prescription.items.get(pk=item_id)
        except PrescriptionItem.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PharmacistPrescriptionItemAudioTranscriptionSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        now = timezone.now()
        PrescriptionItem.objects.filter(pk=item.pk).update(
            transcription_status="processing",
            transcription_requested_at=now,
            transcription_error_message="",
            updated_at=now,
        )
        item.refresh_from_db()

        try:
            transcript = transcribe_audio_file(serializer.validated_data["audio"])
        except AudioTranscriptionError as exc:
            if settings.DEBUG:
                logger.exception("Audio transcription provider failed.")
            provider_error = exc.safe_message
            failed_at = timezone.now()
            PrescriptionItem.objects.filter(pk=item.pk).update(
                transcription_status="failed",
                transcription_provider=get_transcription_provider_name(),
                transcription_completed_at=failed_at,
                transcription_error_message=provider_error,
                updated_at=failed_at,
            )
            item.refresh_from_db()
            return Response(
                {"detail": "Audio transcription failed. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        completed_at = timezone.now()
        PrescriptionItem.objects.filter(pk=item.pk).update(
            instructions_text=transcript,
            instructions_transcript_raw=transcript,
            instructions_transcript_edited=transcript,
            transcription_status="completed",
            transcription_provider=get_transcription_provider_name(),
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
                "detail": "Audio transcribed successfully.",
                "item": TranscribedPrescriptionItemSerializer(item).data,
            }
        )

    def submit(self, request, prescription_id):
        self._ensure_approved()
        try:
            prescription = self._get_prescription(prescription_id)
        except Prescription.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ensure_draft_prescription(prescription)
        serializer = PharmacistPrescriptionSubmitSerializer(
            data=request.data or {},
            context={"prescription": prescription},
        )
        serializer.is_valid(raise_exception=True)
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])
        return Response(
            {
                "detail": "Prescription submitted successfully.",
                "prescription": PharmacistPrescriptionSerializer(prescription).data,
            }
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
            queryset = queryset.filter(status=PrescriptionStatusChoices.SUBMITTED)
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
