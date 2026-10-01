from django.urls import path

from .views import DoctorMedicalVisitViewSet, PatientMedicalVisitViewSet


doctor_visits = DoctorMedicalVisitViewSet.as_view
patient_visits = PatientMedicalVisitViewSet.as_view

urlpatterns = [
    path(
        "doctor/visits/",
        doctor_visits({"get": "list", "post": "create"}),
        name="doctor_visit_list_create",
    ),
    path(
        "doctor/visits/<int:pk>/",
        doctor_visits({"get": "retrieve", "patch": "partial_update"}),
        name="doctor_visit_detail",
    ),
    path(
        "patient/visits/",
        patient_visits({"get": "list"}),
        name="patient_visit_list",
    ),
    path(
        "patient/visits/<int:pk>/",
        patient_visits({"get": "retrieve"}),
        name="patient_visit_detail",
    ),
]
