from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PatientPharmacyViewSet,
    PharmacistPharmacyViewSet,
    PharmacistProfileViewSet,
    PharmacyViewSet,
    PublicContractedPharmacyViewSet,
)

router = DefaultRouter()
router.register("pharmacies", PharmacyViewSet, basename="pharmacy")

pharmacist_me = PharmacistProfileViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update"}
)
pharmacist_pharmacy = PharmacistPharmacyViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update"}
)
public_contracted_pharmacies = PublicContractedPharmacyViewSet.as_view({"get": "list"})
patient_pharmacies = PatientPharmacyViewSet.as_view({"get": "list"})

urlpatterns = [
    path("", include(router.urls)),
    path(
        "auth/contracted-pharmacies/",
        public_contracted_pharmacies,
        name="public-contracted-pharmacies",
    ),
    path(
        "patients/pharmacies/",
        patient_pharmacies,
        name="patient-pharmacies",
    ),
    path("pharmacists/me/", pharmacist_me, name="pharmacist-me"),
    path("pharmacist/me/", pharmacist_me, name="pharmacist-me-singular"),
    path(
        "pharmacist/me/pharmacy/",
        pharmacist_pharmacy,
        name="pharmacist-me-pharmacy",
    ),
]
