from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminPatientAccountViewSet,
    AdminPatientViewSet,
    AdminPatientLoginQRViewSet,
    AdminQRCodeViewSet,
    PharmacistPatientSessionViewSet,
    PatientEnrollmentViewSet,
    PatientManagementViewSet,
    PatientSelfProfileViewSet,
    PatientSessionQRViewSet,
    PatientSessionViewSet,
    PatientSettingsViewSet,
)

router = DefaultRouter()
router.register(
    "patients/enrollments", PatientEnrollmentViewSet, basename="patient-enrollment"
)

patient_generate_qr = PatientManagementViewSet.as_view({"post": "generate_qr"})
patient_session_start = PatientSessionViewSet.as_view({"post": "start_by_qr"})
patient_me = PatientSelfProfileViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update"}
)
patient_settings = PatientSettingsViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update"}
)
patient_session_qr = PatientSessionQRViewSet.as_view({"post": "create"})
pharmacist_sessions = PharmacistPatientSessionViewSet.as_view({"get": "list"})
pharmacist_session_start_by_qr = PharmacistPatientSessionViewSet.as_view(
    {"post": "start_by_qr"}
)
pharmacist_session_end = PharmacistPatientSessionViewSet.as_view({"post": "end"})
admin_patient_create_account = AdminPatientAccountViewSet.as_view(
    {"post": "create_account"}
)
admin_patients = AdminPatientViewSet.as_view({"get": "list"})
admin_patient_detail = AdminPatientViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)
admin_patient_generate_qr = AdminPatientViewSet.as_view({"post": "generate_qr"})
admin_qr_codes = AdminQRCodeViewSet.as_view({"get": "list"})
admin_qr_code_detail = AdminQRCodeViewSet.as_view({"get": "retrieve"})
admin_qr_code_regenerate = AdminQRCodeViewSet.as_view({"post": "regenerate"})
admin_qr_code_disable = AdminQRCodeViewSet.as_view({"post": "disable"})
admin_qr_code_reactivate = AdminQRCodeViewSet.as_view({"post": "reactivate"})
admin_patient_login_qr = AdminPatientLoginQRViewSet.as_view({"post": "generate"})
admin_patient_login_qr_revoke = AdminPatientLoginQRViewSet.as_view({"post": "revoke"})

urlpatterns = [
    path("admin/patients/", admin_patients, name="admin-patient-list"),
    path(
        "admin/patients/<int:pk>/",
        admin_patient_detail,
        name="admin-patient-detail",
    ),
    path(
        "admin/patients/<int:pk>/generate-qr/",
        admin_patient_generate_qr,
        name="admin-patient-generate-qr",
    ),
    path("admin/qr-codes/", admin_qr_codes, name="admin-qr-code-list"),
    path(
        "admin/qr-codes/<int:pk>/",
        admin_qr_code_detail,
        name="admin-qr-code-detail",
    ),
    path(
        "admin/qr-codes/<int:pk>/regenerate/",
        admin_qr_code_regenerate,
        name="admin-qr-code-regenerate",
    ),
    path(
        "admin/qr-codes/<int:pk>/disable/",
        admin_qr_code_disable,
        name="admin-qr-code-disable",
    ),
    path(
        "admin/qr-codes/<int:pk>/reactivate/",
        admin_qr_code_reactivate,
        name="admin-qr-code-reactivate",
    ),
    path(
        "admin/patients/create-account/",
        admin_patient_create_account,
        name="admin-patient-create-account",
    ),
    path(
        "admin/patients/<int:patient_id>/login-qr/",
        admin_patient_login_qr,
        name="admin-patient-login-qr",
    ),
    path(
        "admin/patients/<int:patient_id>/login-qr/revoke/",
        admin_patient_login_qr_revoke,
        name="admin-patient-login-qr-revoke",
    ),
    path("", include(router.urls)),
    path("patients/me/", patient_me, name="patient-me"),
    path("patients/me/settings/", patient_settings, name="patient-settings"),
    path("patients/me/session-qr/", patient_session_qr, name="patient-session-qr"),
    path("pharmacist/sessions/", pharmacist_sessions, name="pharmacist-sessions"),
    path(
        "pharmacist/sessions/start-by-qr/",
        pharmacist_session_start_by_qr,
        name="pharmacist-session-start-by-qr",
    ),
    path(
        "pharmacist/sessions/<int:session_id>/end/",
        pharmacist_session_end,
        name="pharmacist-session-end",
    ),
    path(
        "patients/<int:pk>/generate-qr/",
        patient_generate_qr,
        name="patient-generate-qr",
    ),
    path(
        "patient-sessions/start-by-qr/",
        patient_session_start,
        name="patient-session-start-by-qr",
    ),
]
