from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminPharmacistViewSet,
    AdminPharmacyViewSet,
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
admin_pharmacies = AdminPharmacyViewSet.as_view({"get": "list", "post": "create"})
admin_pharmacy_detail = AdminPharmacyViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)
admin_pharmacists = AdminPharmacistViewSet.as_view({"get": "list", "post": "create"})
admin_pharmacist_detail = AdminPharmacistViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    path("admin/pharmacies/", admin_pharmacies, name="admin-pharmacy-list"),
    path(
        "admin/pharmacies/<int:pk>/",
        admin_pharmacy_detail,
        name="admin-pharmacy-detail",
    ),
    path("admin/pharmacists/", admin_pharmacists, name="admin-pharmacist-list"),
    path(
        "admin/pharmacists/<int:pk>/",
        admin_pharmacist_detail,
        name="admin-pharmacist-detail",
    ),
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
