from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.api_errors import validation_error_payload
from common.permissions import (
    CanManagePatients,
    IsApprovedPharmacistRole,
    IsPharmacistRole,
    IsPatientRole,
    pharmacist_can_access_patient,
)

from common.choices import PatientSessionAccessTypeChoices

from .models import PatientEnrollment, PatientProfile, PatientSession, PatientSettings
from .serializers import (
    AdminPatientCreateAccountSerializer,
    CreatePatientAccountSerializer,
    GeneratePatientLoginQRSerializer,
    GeneratePatientQRSerializer,
    GeneratePatientSessionQRSerializer,
    PharmacistPatientSessionSerializer,
    PatientEnrollmentSerializer,
    PatientSelfProfileSerializer,
    PatientSettingsSerializer,
    PatientSessionSerializer,
    RevokePatientLoginQRSerializer,
    StartPatientSessionByQRSerializer,
    StartPatientSessionSerializer,
    build_session_response_payload,
)
from .services import build_patient_summary


class PatientEnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = PatientEnrollmentSerializer
    permission_classes = [IsAuthenticated, CanManagePatients]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = PatientEnrollment.objects.select_related(
            "organization",
            "created_by",
            "patient_profile",
        )
        staff_profile = getattr(self.request.user, "organization_staff_profile", None)
        if self.request.user.is_superuser or staff_profile is None:
            return queryset
        return queryset.filter(organization=staff_profile.organization)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="create-account")
    def create_account(self, request, pk=None):
        enrollment = self.get_object()
        serializer = CreatePatientAccountSerializer(
            data=request.data,
            context={"enrollment": enrollment},
        )
        serializer.is_valid(raise_exception=True)
        patient_profile = serializer.save()
        return Response(
            {
                "patient_id": patient_profile.id,
                "user_id": patient_profile.user_id,
                "qr_code_value": patient_profile.qr_code_value,
            },
            status=status.HTTP_201_CREATED,
        )


class PatientManagementViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PatientProfile.objects.select_related("organization", "user")
    permission_classes = [IsAuthenticated, CanManagePatients]

    @action(detail=True, methods=["post"], url_path="generate-qr")
    def generate_qr(self, request, pk=None):
        patient = self.get_object()
        serializer = GeneratePatientQRSerializer(
            data=request.data,
            context={"patient": patient},
        )
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload)

    def get_queryset(self):
        queryset = super().get_queryset()
        staff_profile = getattr(self.request.user, "organization_staff_profile", None)
        if self.request.user.is_superuser or staff_profile is None:
            return queryset
        return queryset.filter(organization=staff_profile.organization)


class PatientSelfProfileViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPatientRole]

    def _get_patient_profile(self):
        return self.request.user.patient_profile

    def retrieve(self, request):
        serializer = PatientSelfProfileSerializer(self._get_patient_profile())
        return Response(serializer.data)

    def partial_update(self, request):
        patient = self._get_patient_profile()
        serializer = PatientSelfProfileSerializer(
            patient,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PatientSelfProfileSerializer(patient).data)


class PatientSettingsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPatientRole]

    def _get_settings(self):
        patient = self.request.user.patient_profile
        settings, _ = PatientSettings.objects.get_or_create(patient=patient)
        return settings

    def retrieve(self, request):
        serializer = PatientSettingsSerializer(self._get_settings())
        return Response(serializer.data)

    def partial_update(self, request):
        settings = self._get_settings()
        serializer = PatientSettingsSerializer(
            settings,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PatientSessionQRViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPatientRole]

    def create(self, request):
        patient = request.user.patient_profile
        serializer = GeneratePatientSessionQRSerializer(context={"patient": patient})
        return Response(serializer.save(), status=status.HTTP_201_CREATED)


class AdminPatientAccountViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, CanManagePatients]

    def create_account(self, request):
        serializer = AdminPatientCreateAccountSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(serializer.to_response(result), status=status.HTTP_201_CREATED)


class AdminPatientLoginQRViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, CanManagePatients]

    def _get_patient(self, patient_id):
        queryset = PatientProfile.objects.select_related("user", "organization")
        staff_profile = getattr(self.request.user, "organization_staff_profile", None)
        if not self.request.user.is_superuser and staff_profile is not None:
            queryset = queryset.filter(organization=staff_profile.organization)
        return get_object_or_404(queryset, pk=patient_id)

    def generate(self, request, patient_id):
        patient = self._get_patient(patient_id)
        serializer = GeneratePatientLoginQRSerializer(
            data=request.data or {},
            context={"request": request, "patient": patient},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_201_CREATED)

    def revoke(self, request, patient_id):
        patient = self._get_patient(patient_id)
        serializer = RevokePatientLoginQRSerializer(
            data=request.data or {},
            context={"request": request, "patient": patient},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save())


class PatientSessionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]

    @action(detail=False, methods=["post"], url_path="start-by-qr")
    def start_by_qr(self, request):
        serializer = StartPatientSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = get_object_or_404(
            PatientProfile.objects.select_related("medical_info"),
            qr_code_value=serializer.validated_data["qr_code_value"],
            qr_is_active=True,
        )
        if not pharmacist_can_access_patient(request.user, patient):
            raise PermissionDenied(
                "You do not have workflow access to this patient record."
            )
        pharmacist_profile = request.user.pharmacist_profile
        session = PatientSession.objects.create(
            patient=patient,
            pharmacist=pharmacist_profile,
            pharmacy=pharmacist_profile.pharmacy,
            access_type=PatientSessionAccessTypeChoices.QR_SCAN,
            qr_code_value_snapshot=serializer.validated_data["qr_code_value"],
        )
        return Response(
            {
                "session": PatientSessionSerializer(session).data,
                "patient_summary": build_patient_summary(patient),
            }
        )


class PharmacistPatientSessionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]

    def _get_pharmacist_profile(self):
        return self.request.user.pharmacist_profile

    def _get_queryset(self):
        pharmacist = self._get_pharmacist_profile()
        queryset = PatientSession.objects.select_related(
            "patient",
            "patient__user",
            "patient__medical_info",
            "pharmacist",
            "pharmacy",
        ).filter(pharmacist=pharmacist)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def list(self, request):
        serializer = PharmacistPatientSessionSerializer(self._get_queryset(), many=True)
        return Response(serializer.data)

    def start_by_qr(self, request):
        pharmacist = self._get_pharmacist_profile()
        if not pharmacist.is_approved:
            raise PermissionDenied("Pharmacist account is not approved.")

        serializer = StartPatientSessionByQRSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        session_qr = serializer.validated_data["session_qr"]
        patient = session_qr.patient
        if not pharmacist_can_access_patient(request.user, patient):
            raise PermissionDenied("You do not have workflow access to this patient.")

        active_session = (
            PatientSession.objects.select_related("patient", "pharmacist", "pharmacy")
            .filter(
                patient=patient,
                pharmacist=pharmacist,
                status=PatientSession.STATUS_ACTIVE,
                ended_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            .order_by("-started_at")
            .first()
        )
        session_qr.mark_used()
        if active_session:
            return Response(build_session_response_payload(active_session))

        session = PatientSession.objects.create(
            patient=patient,
            pharmacist=pharmacist,
            pharmacy=pharmacist.pharmacy,
            access_type=PatientSessionAccessTypeChoices.QR_SCAN,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )
        return Response(
            build_session_response_payload(session), status=status.HTTP_201_CREATED
        )

    def end(self, request, session_id):
        session = get_object_or_404(self._get_queryset(), pk=session_id)
        session.status = PatientSession.STATUS_COMPLETED
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at", "updated_at"])
        return Response(
            {
                "detail": "Session ended successfully",
                "session": {
                    "id": session.id,
                    "status": "ended",
                    "ended_at": session.ended_at,
                },
            }
        )
