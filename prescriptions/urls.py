from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PatientPrescriptionViewSet,
    PharmacistPrescriptionViewSet,
    PrescriptionItemViewSet,
    PrescriptionViewSet,
)

router = DefaultRouter()
router.register("prescriptions", PrescriptionViewSet, basename="prescription")
router.register(
    "prescriptions/items", PrescriptionItemViewSet, basename="prescription-item"
)
router.register(
    "patients/me/prescriptions",
    PatientPrescriptionViewSet,
    basename="patient-prescription",
)

pharmacist_prescriptions = PharmacistPrescriptionViewSet.as_view(
    {"get": "list", "post": "create"}
)
pharmacist_prescription_detail = PharmacistPrescriptionViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update"}
)
pharmacist_prescription_items = PharmacistPrescriptionViewSet.as_view(
    {"post": "add_item"}
)
pharmacist_prescription_item_detail = PharmacistPrescriptionViewSet.as_view(
    {"patch": "update_item", "delete": "delete_item"}
)
pharmacist_prescription_item_transcribe_audio = PharmacistPrescriptionViewSet.as_view(
    {"post": "transcribe_audio"}
)
pharmacist_prescription_item_approve_transcript = PharmacistPrescriptionViewSet.as_view(
    {"post": "approve_transcript"}
)
pharmacist_prescription_item_generate_sign = PharmacistPrescriptionViewSet.as_view(
    {"post": "generate_sign"}
)
pharmacist_prescription_submit = PharmacistPrescriptionViewSet.as_view(
    {"post": "submit"}
)

urlpatterns = [
    *router.urls,
    path(
        "pharmacist/prescriptions/",
        pharmacist_prescriptions,
        name="pharmacist-prescriptions",
    ),
    path(
        "pharmacist/prescriptions/<int:prescription_id>/",
        pharmacist_prescription_detail,
        name="pharmacist-prescription-detail",
    ),
    path(
        "pharmacist/prescriptions/<int:prescription_id>/items/",
        pharmacist_prescription_items,
        name="pharmacist-prescription-items",
    ),
    path(
        "pharmacist/prescriptions/<int:prescription_id>/items/<int:item_id>/",
        pharmacist_prescription_item_detail,
        name="pharmacist-prescription-item-detail",
    ),
    path(
        (
            "pharmacist/prescriptions/<int:prescription_id>/items/"
            "<int:item_id>/transcribe-audio/"
        ),
        pharmacist_prescription_item_transcribe_audio,
        name="pharmacist-prescription-item-transcribe-audio",
    ),
    path(
        (
            "pharmacist/prescriptions/<int:prescription_id>/items/"
            "<int:item_id>/approve-transcript/"
        ),
        pharmacist_prescription_item_approve_transcript,
        name="pharmacist-prescription-item-approve-transcript",
    ),
    path(
        (
            "pharmacist/prescriptions/<int:prescription_id>/items/"
            "<int:item_id>/generate-sign/"
        ),
        pharmacist_prescription_item_generate_sign,
        name="pharmacist-prescription-item-generate-sign",
    ),
    path(
        "pharmacist/prescriptions/<int:prescription_id>/submit/",
        pharmacist_prescription_submit,
        name="pharmacist-prescription-submit",
    ),
]
