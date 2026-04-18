from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import (
    CanManagePatients,
    IsApprovedPharmacistRole,
    pharmacist_can_access_patient,
)

from common.choices import PatientSessionAccessTypeChoices

from .models import PatientEnrollment, PatientProfile, PatientSession
from .serializers import (
    CreatePatientAccountSerializer,
    GeneratePatientQRSerializer,
    PatientEnrollmentSerializer,
    PatientSessionSerializer,
    StartPatientSessionSerializer,
)
from .services import build_patient_summary


class PatientEnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = PatientEnrollmentSerializer
    permission_classes = [IsAuthenticated, CanManagePatients]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = PatientEnrollment.objects.select_related(
            'organization',
            'created_by',
            'patient_profile',
        )
        staff_profile = getattr(self.request.user, 'organization_staff_profile', None)
        if self.request.user.is_superuser or staff_profile is None:
            return queryset
        return queryset.filter(organization=staff_profile.organization)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='create-account')
    def create_account(self, request, pk=None):
        enrollment = self.get_object()
        serializer = CreatePatientAccountSerializer(
            data=request.data,
            context={'enrollment': enrollment},
        )
        serializer.is_valid(raise_exception=True)
        patient_profile = serializer.save()
        return Response(
            {
                'patient_id': patient_profile.id,
                'user_id': patient_profile.user_id,
                'qr_code_value': patient_profile.qr_code_value,
            },
            status=status.HTTP_201_CREATED,
        )


class PatientManagementViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PatientProfile.objects.select_related('organization', 'user')
    permission_classes = [IsAuthenticated, CanManagePatients]

    @action(detail=True, methods=['post'], url_path='generate-qr')
    def generate_qr(self, request, pk=None):
        patient = self.get_object()
        serializer = GeneratePatientQRSerializer(
            data=request.data,
            context={'patient': patient},
        )
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload)

    def get_queryset(self):
        queryset = super().get_queryset()
        staff_profile = getattr(self.request.user, 'organization_staff_profile', None)
        if self.request.user.is_superuser or staff_profile is None:
            return queryset
        return queryset.filter(organization=staff_profile.organization)


class PatientSessionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]

    @action(detail=False, methods=['post'], url_path='start-by-qr')
    def start_by_qr(self, request):
        serializer = StartPatientSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = get_object_or_404(
            PatientProfile.objects.select_related('medical_info'),
            qr_code_value=serializer.validated_data['qr_code_value'],
            qr_is_active=True,
        )
        if not pharmacist_can_access_patient(request.user, patient):
            raise PermissionDenied(
                'You do not have workflow access to this patient record.'
            )
        pharmacist_profile = request.user.pharmacist_profile
        session = PatientSession.objects.create(
            patient=patient,
            pharmacist=pharmacist_profile,
            pharmacy=pharmacist_profile.pharmacy,
            access_type=PatientSessionAccessTypeChoices.QR_SCAN,
            qr_code_value_snapshot=serializer.validated_data['qr_code_value'],
        )
        return Response(
            {
                'session': PatientSessionSerializer(session).data,
                'patient_summary': build_patient_summary(patient),
            }
        )
