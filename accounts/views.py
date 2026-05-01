from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from pharmacies.serializers import PharmacistRegisterSerializer

from .serializers import (
    AuthMeSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    PatientRegistrationOTPRequestSerializer,
    PatientQRLoginSerializer,
    PatientSelfRegisterSerializer,
    UserSerializer,
)


class AuthViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in {
            "pharmacist_register",
            "login",
            "patient_self_register",
            "patient_register",
            "patient_register_request_otp",
            "patient_qr_login",
        }:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def _build_auth_response(self, user, status_code=status.HTTP_200_OK):
        refresh = RefreshToken.for_user(user)
        payload = AuthMeSerializer(user).data
        payload["access"] = str(refresh.access_token)
        payload["refresh"] = str(refresh)
        return Response(
            payload,
            status=status_code,
        )

    @action(detail=False, methods=["post"], url_path="pharmacist/register")
    def pharmacist_register(self, request):
        serializer = PharmacistRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return self._build_auth_response(profile.user, status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        return self._build_auth_response(serializer.validated_data["user"])

    @action(detail=False, methods=["post"], url_path="patient/self-register")
    def patient_self_register(self, request):
        serializer = PatientSelfRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return self._build_auth_response(user, status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="patient/register")
    def patient_register(self, request):
        return self.patient_self_register(request)

    @action(detail=False, methods=["post"], url_path="patient/register/request-otp")
    def patient_register_request_otp(self, request):
        serializer = PatientRegistrationOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save())

    @action(detail=False, methods=["post"], url_path="patient/qr-login")
    def patient_qr_login(self, request):
        serializer = PatientQRLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._build_auth_response(serializer.validated_data["user"])

    @action(detail=False, methods=["post"], url_path="logout")
    def logout(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError as exc:
            raise ValidationError({"refresh": str(exc)})
        return Response({"detail": "Logged out successfully."})

    @action(detail=False, methods=["post"], url_path="change-password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password changed successfully."})

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        return Response(AuthMeSerializer(request.user).data)
