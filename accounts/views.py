from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from pharmacies.serializers import PharmacistRegisterSerializer
from common.choices import ApprovalStatusChoices, RoleChoices

from .serializers import (
    AuthMeSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    PENDING_ACCOUNT_DETAIL,
    PatientRegistrationOTPRequestSerializer,
    PatientQRLoginSerializer,
    PatientSelfRegisterSerializer,
    REJECTED_ACCOUNT_DETAIL,
    RegistrationOTPRequestSerializer,
)

User = get_user_model()


class AuthViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in {
            "pharmacist_register",
            "login",
            "patient_self_register",
            "patient_register",
            "patient_register_request_otp",
            "pharmacist_register_request_otp",
            "register_request_otp",
            "patient_qr_login",
        }:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def _can_manage_registration_requests(self, user):
        if user.is_superuser:
            return True
        staff_profile = getattr(user, "organization_staff_profile", None)
        if staff_profile:
            return bool(
                staff_profile.can_manage_patients
                or staff_profile.can_manage_pharmacists
            )
        return bool(user.is_staff)

    def _manageable_registration_roles(self, user):
        if user.is_superuser:
            return [RoleChoices.PATIENT, RoleChoices.PHARMACIST]
        staff_profile = getattr(user, "organization_staff_profile", None)
        if staff_profile:
            roles = []
            if staff_profile.can_manage_patients:
                roles.append(RoleChoices.PATIENT)
            if staff_profile.can_manage_pharmacists:
                roles.append(RoleChoices.PHARMACIST)
            return roles
        if user.is_staff:
            return [RoleChoices.PATIENT, RoleChoices.PHARMACIST]
        return []

    def _can_manage_user_role(self, manager, target_user):
        return target_user.role in self._manageable_registration_roles(manager)

    def _role_approval_denied(self):
        return Response(
            {"detail": "You do not have permission to approve this user role."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def _registration_management_denied(self):
        return Response(
            {"detail": "You do not have permission to manage registration requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def _approval_block_response(self, user):
        if user.approval_status == ApprovalStatusChoices.PENDING:
            return Response(
                {
                    "detail": PENDING_ACCOUNT_DETAIL,
                    "approval_status": ApprovalStatusChoices.PENDING,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.approval_status == ApprovalStatusChoices.REJECTED:
            return Response(
                {
                    "detail": REJECTED_ACCOUNT_DETAIL,
                    "approval_status": ApprovalStatusChoices.REJECTED,
                    "rejection_reason": user.rejection_reason,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if (
            user.role == RoleChoices.PHARMACIST
            and hasattr(user, "pharmacist_profile")
            and not user.pharmacist_profile.is_approved
        ):
            return Response(
                {
                    "detail": PENDING_ACCOUNT_DETAIL,
                    "approval_status": ApprovalStatusChoices.PENDING,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def _blacklist_user_tokens(self, user):
        for outstanding_token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding_token)

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
        return Response(serializer.to_response(profile), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        blocked_response = self._approval_block_response(user)
        if blocked_response:
            return blocked_response
        return self._build_auth_response(user)

    @action(detail=False, methods=["post"], url_path="patient/self-register")
    def patient_self_register(self, request):
        serializer = PatientSelfRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(serializer.to_response(user), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="patient/register")
    def patient_register(self, request):
        return self.patient_self_register(request)

    @action(detail=False, methods=["post"], url_path="patient/register/request-otp")
    def patient_register_request_otp(self, request):
        serializer = PatientRegistrationOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save())

    @action(detail=False, methods=["post"], url_path="pharmacist/register/request-otp")
    def pharmacist_register_request_otp(self, request):
        data = request.data.copy()
        data["role"] = "pharmacist"
        serializer = RegistrationOTPRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save())

    @action(detail=False, methods=["post"], url_path="register/request-otp")
    def register_request_otp(self, request):
        serializer = RegistrationOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save())

    @action(detail=False, methods=["post"], url_path="patient/qr-login")
    def patient_qr_login(self, request):
        serializer = PatientQRLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        blocked_response = self._approval_block_response(user)
        if blocked_response:
            return blocked_response
        return self._build_auth_response(user)

    @action(detail=False, methods=["get"], url_path="admin/registration-requests")
    def registration_requests(self, request):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        users = User.objects.filter(
            approval_status=ApprovalStatusChoices.PENDING,
            role__in=self._manageable_registration_roles(request.user),
        ).order_by("-created_at")
        return Response(
            [
                {
                    "id": user.id,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "role": user.role,
                    "approval_status": user.approval_status,
                    "created_at": user.created_at,
                }
                for user in users
            ]
        )

    @action(detail=True, methods=["post"], url_path="admin/users/approve")
    def approve_user(self, request, pk=None):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        user = get_object_or_404(User, pk=pk)
        if not self._can_manage_user_role(request.user, user):
            return self._role_approval_denied()
        user.approval_status = ApprovalStatusChoices.APPROVED
        user.approved_at = timezone.now()
        user.approved_by = request.user
        user.rejection_reason = ""
        user.is_verified = True
        user.save(
            update_fields=[
                "approval_status",
                "approved_at",
                "approved_by",
                "rejection_reason",
                "is_verified",
                "updated_at",
            ]
        )
        if user.role == RoleChoices.PHARMACIST and hasattr(user, "pharmacist_profile"):
            profile = user.pharmacist_profile
            profile.is_approved = True
            profile.save(update_fields=["is_approved", "updated_at"])
        return Response(
            {
                "detail": "User approved successfully.",
                "user": {
                    "id": user.id,
                    "phone_number": user.phone_number,
                    "role": user.role,
                    "approval_status": user.approval_status,
                },
            }
        )

    @action(detail=True, methods=["post"], url_path="admin/users/reject")
    def reject_user(self, request, pk=None):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        user = get_object_or_404(User, pk=pk)
        if not self._can_manage_user_role(request.user, user):
            return self._role_approval_denied()
        user.approval_status = ApprovalStatusChoices.REJECTED
        user.rejection_reason = request.data.get("reason", "")
        user.is_verified = False
        user.save(
            update_fields=[
                "approval_status",
                "rejection_reason",
                "is_verified",
                "updated_at",
            ]
        )
        if user.role == RoleChoices.PHARMACIST and hasattr(user, "pharmacist_profile"):
            profile = user.pharmacist_profile
            profile.is_approved = False
            profile.save(update_fields=["is_approved", "updated_at"])
        self._blacklist_user_tokens(user)
        return Response(
            {
                "detail": "User rejected successfully.",
                "user": {
                    "id": user.id,
                    "phone_number": user.phone_number,
                    "role": user.role,
                    "approval_status": user.approval_status,
                },
            }
        )

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
