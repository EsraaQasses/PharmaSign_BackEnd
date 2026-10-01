from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from common.permissions import IsApprovedDoctorRole, IsPatientRole

from .models import MedicalVisit
from .serializers import MedicalVisitSerializer


class DoctorMedicalVisitViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MedicalVisitSerializer
    permission_classes = [IsAuthenticated, IsApprovedDoctorRole]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        profile = getattr(self.request.user, "doctor_profile", None)
        if profile is None:
            return MedicalVisit.objects.none()
        return (
            MedicalVisit.objects.select_related("patient", "patient__user", "doctor")
            .prefetch_related("medications")
            .filter(doctor=profile)
        )

    def perform_create(self, serializer):
        serializer.save(doctor=self.request.user.doctor_profile)


class PatientMedicalVisitViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MedicalVisitSerializer
    permission_classes = [IsAuthenticated, IsPatientRole]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        patient = getattr(self.request.user, "patient_profile", None)
        if patient is None:
            return MedicalVisit.objects.none()
        return (
            MedicalVisit.objects.select_related("patient", "patient__user", "doctor")
            .prefetch_related("medications")
            .filter(patient=patient)
        )
