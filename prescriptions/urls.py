from django.urls import include
from rest_framework.routers import DefaultRouter

from .views import PatientPrescriptionViewSet, PrescriptionItemViewSet, PrescriptionViewSet

router = DefaultRouter()
router.register('prescriptions', PrescriptionViewSet, basename='prescription')
router.register('prescriptions/items', PrescriptionItemViewSet, basename='prescription-item')
router.register(
    'patients/me/prescriptions',
    PatientPrescriptionViewSet,
    basename='patient-prescription',
)

urlpatterns = router.urls
