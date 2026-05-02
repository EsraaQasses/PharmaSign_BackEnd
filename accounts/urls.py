from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import AuthViewSet


app_name = "accounts"

auth_viewset = AuthViewSet.as_view

urlpatterns = [
    path(
        "auth/pharmacist/register/",
        auth_viewset({"post": "pharmacist_register"}),
        name="pharmacist_register",
    ),
    path(
        "auth/register/request-otp/",
        auth_viewset({"post": "register_request_otp"}),
        name="register_request_otp",
    ),
    path(
        "auth/pharmacist/register/request-otp/",
        auth_viewset({"post": "pharmacist_register_request_otp"}),
        name="pharmacist_register_request_otp",
    ),
    path("auth/login/", auth_viewset({"post": "login"}), name="login"),
    path(
        "auth/patient/self-register/",
        auth_viewset({"post": "patient_self_register"}),
        name="patient_self_register",
    ),
    path(
        "auth/patient/register/",
        auth_viewset({"post": "patient_register"}),
        name="patient_register",
    ),
    path(
        "auth/patient/register/request-otp/",
        auth_viewset({"post": "patient_register_request_otp"}),
        name="patient_register_request_otp",
    ),
    path(
        "auth/patient/qr-login/",
        auth_viewset({"post": "patient_qr_login"}),
        name="patient_qr_login",
    ),
    path(
        "admin/registration-requests/",
        auth_viewset({"get": "registration_requests"}),
        name="registration_requests",
    ),
    path(
        "admin/users/<int:pk>/approve/",
        AuthViewSet.as_view({"post": "approve_user"}),
        name="approve_user",
    ),
    path(
        "admin/users/<int:pk>/reject/",
        AuthViewSet.as_view({"post": "reject_user"}),
        name="reject_user",
    ),
    path("auth/logout/", auth_viewset({"post": "logout"}), name="logout"),
    path(
        "auth/change-password/",
        auth_viewset({"post": "change_password"}),
        name="change_password",
    ),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me/", auth_viewset({"get": "me"}), name="me"),
]
