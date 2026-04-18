from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.choices import PrescriptionAccessTypeChoices, PrescriptionStatusChoices, RoleChoices
from common.permissions import (
    CanManagePatients,
    IsApprovedPharmacistRole,
    IsPatientRole,
    has_patient_management_access,
    pharmacist_can_access_patient,
)

from .models import Prescription, PrescriptionItem
from .serializers import (
    PrescriptionConfirmSerializer,
    PrescriptionCreateSerializer,
    PrescriptionItemCreateSerializer,
    PrescriptionItemSerializer,
    PrescriptionItemTranscriptionRequestSerializer,
    PrescriptionItemUpdateSerializer,
    PrescriptionSerializer,
)
from .services import log_prescription_access, transcribe_prescription_item


class PrescriptionViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Prescription.objects.select_related(
        'patient',
        'patient__user',
        'patient__organization',
        'pharmacist',
        'pharmacist__user',
        'pharmacy',
    ).prefetch_related('items', 'patient__medical_info')
    http_method_names = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return PrescriptionCreateSerializer
        if self.action == 'add_item':
            return PrescriptionItemCreateSerializer
        if self.action == 'confirm':
            return PrescriptionConfirmSerializer
        return PrescriptionSerializer

    def get_permissions(self):
        if self.action in {'create', 'add_item', 'confirm'}:
            permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]
        elif self.request.user.is_authenticated and self.request.user.role == RoleChoices.ADMIN:
            permission_classes = [IsAuthenticated, CanManagePatients]
        elif self.request.user.is_authenticated and self.request.user.role == RoleChoices.PATIENT:
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
            staff_profile = getattr(user, 'organization_staff_profile', None)
            if staff_profile is None:
                return queryset
            return queryset.filter(patient__organization=staff_profile.organization)
        if user.role == RoleChoices.PHARMACIST:
            pharmacist_profile = getattr(user, 'pharmacist_profile', None)
            if pharmacist_profile is None:
                return queryset.none()
            return queryset.filter(pharmacist=pharmacist_profile)
        if user.role == RoleChoices.PATIENT:
            patient_profile = getattr(user, 'patient_profile', None)
            if patient_profile is None:
                return queryset.none()
            return queryset.filter(patient=patient_profile)
        return queryset.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = serializer.validated_data['patient']
        if not pharmacist_can_access_patient(request.user, patient):
            raise PermissionDenied('You do not have workflow access to this patient.')
        pharmacist_profile = request.user.pharmacist_profile
        prescription = serializer.save(
            pharmacist=pharmacist_profile,
            pharmacy=pharmacist_profile.pharmacy,
            status=PrescriptionStatusChoices.DRAFT,
        )
        return Response(
            PrescriptionSerializer(prescription, context=self.get_serializer_context()).data,
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

    @action(detail=True, methods=['post'], url_path='items')
    def add_item(self, request, pk=None):
        prescription = self.get_object()
        if prescription.pharmacist.user_id != request.user.id:
            raise PermissionDenied('Only the prescription pharmacist can add items.')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(prescription=prescription)
        return Response(
            PrescriptionItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, pk=None):
        prescription = self.get_object()
        if prescription.pharmacist.user_id != request.user.id:
            raise PermissionDenied('Only the prescription pharmacist can confirm it.')
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        prescription.status = PrescriptionStatusChoices.CONFIRMED
        prescription.save(update_fields=['status', 'updated_at'])
        log_prescription_access(
            prescription,
            request.user,
            PrescriptionAccessTypeChoices.CONFIRM,
        )
        return Response(PrescriptionSerializer(prescription).data)


class PrescriptionItemViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = PrescriptionItemUpdateSerializer
    permission_classes = [IsAuthenticated, IsApprovedPharmacistRole]
    queryset = PrescriptionItem.objects.select_related('prescription', 'prescription__pharmacist')
    http_method_names = ['patch', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'transcribe':
            return PrescriptionItemTranscriptionRequestSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        pharmacist_profile = getattr(self.request.user, 'pharmacist_profile', None)
        if pharmacist_profile is None:
            return super().get_queryset().none()
        return super().get_queryset().filter(prescription__pharmacist=pharmacist_profile)

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        log_prescription_access(
            self.get_object().prescription,
            request.user,
            PrescriptionAccessTypeChoices.ITEM_UPDATE,
        )
        return response

    @action(detail=True, methods=['post'], url_path='transcribe')
    def transcribe(self, request, pk=None):
        item = self.get_object()
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            item = transcribe_prescription_item(
                item,
                requested_by=request.user,
                force=serializer.validated_data['force'],
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(PrescriptionItemSerializer(item).data)


class PatientPrescriptionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAuthenticated, IsPatientRole]
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        patient_profile = getattr(self.request.user, 'patient_profile', None)
        if patient_profile is None:
            return Prescription.objects.none()
        return (
            Prescription.objects.select_related(
                'pharmacist',
                'pharmacist__user',
                'pharmacy',
                'patient',
                'patient__user',
            )
            .prefetch_related('items')
            .filter(patient=patient_profile)
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
