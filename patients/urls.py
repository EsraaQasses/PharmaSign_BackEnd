from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PatientEnrollmentViewSet, PatientManagementViewSet, PatientSessionViewSet

router = DefaultRouter()
router.register('patients/enrollments', PatientEnrollmentViewSet, basename='patient-enrollment')

patient_generate_qr = PatientManagementViewSet.as_view({'post': 'generate_qr'})
patient_session_start = PatientSessionViewSet.as_view({'post': 'start_by_qr'})

urlpatterns = [
    path('', include(router.urls)),
    path('patients/<int:pk>/generate-qr/', patient_generate_qr, name='patient-generate-qr'),
    path(
        'patient-sessions/start-by-qr/',
        patient_session_start,
        name='patient-session-start-by-qr',
    ),
]
