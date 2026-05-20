from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from common.api_errors import error_response, validation_error_payload
from common.choices import (
    ApprovalStatusChoices,
    HearingConditionTypeChoices,
    RoleChoices,
)
from common.permissions import is_admin_role
from patients.models import PatientProfile
from pharmacies.serializers import PharmacistRegisterSerializer
from pharmacies.models import PharmacistProfile, Pharmacy
from prescriptions.models import Prescription, SignQualityReport

from .serializers import (
    AdminApprovalRequestSerializer,
    AdminAuthMeSerializer,
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
from .services import OTPDeliveryError

User = get_user_model()


class AdminPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


class AuthViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in {
            "pharmacist_register",
            "login",
            "admin_login",
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
                    "code": "approval_pending",
                    "approval_status": ApprovalStatusChoices.PENDING,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.approval_status == ApprovalStatusChoices.REJECTED:
            return Response(
                {
                    "detail": REJECTED_ACCOUNT_DETAIL,
                    "code": "approval_rejected",
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
                    "code": "approval_pending",
                    "approval_status": ApprovalStatusChoices.PENDING,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def _blacklist_user_tokens(self, user):
        for outstanding_token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding_token)

    def _approve_user_object(self, user, approved_by):
        user.approval_status = ApprovalStatusChoices.APPROVED
        user.approved_at = timezone.now()
        user.approved_by = approved_by
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
        return user

    def _reject_user_object(self, user, reason):
        user.approval_status = ApprovalStatusChoices.REJECTED
        user.rejection_reason = reason
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
        return user

    def _build_auth_response(self, user, status_code=status.HTTP_200_OK):
        refresh = RefreshToken.for_user(user)
        payload = AuthMeSerializer(user).data
        payload["access"] = str(refresh.access_token)
        payload["refresh"] = str(refresh)
        return Response(
            payload,
            status=status_code,
        )

    def _build_admin_auth_response(self, user, status_code=status.HTTP_200_OK):
        refresh = RefreshToken.for_user(user)
        payload = AdminAuthMeSerializer(user).data
        payload["access"] = str(refresh.access_token)
        payload["refresh"] = str(refresh)
        return Response(payload, status=status_code)

    def _otp_delivery_failed_response(self, exc):
        delivery = {
            "channel": exc.delivery.get("channel"),
            "sent": False,
            "error": exc.delivery.get("error") or "OTP delivery failed.",
        }
        return Response(
            {
                "detail": "OTP delivery failed.",
                "code": "otp_delivery_failed",
                "delivery": delivery,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def _admin_denied_response(self):
        return Response(
            {
                "detail": "Admin access is required.",
                "code": "admin_access_required",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    def _ensure_admin_response(self, user):
        if not is_admin_role(user):
            return self._admin_denied_response()
        return None

    def _manageable_dashboard_roles(self, user):
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
        return [RoleChoices.PATIENT, RoleChoices.PHARMACIST]

    def _admin_staff_organization(self, user):
        if user.is_superuser:
            return None
        staff_profile = getattr(user, "organization_staff_profile", None)
        return getattr(staff_profile, "organization", None)

    def _dashboard_patient_queryset(self, user):
        queryset = PatientProfile.objects.select_related("user", "organization")
        organization = self._admin_staff_organization(user)
        if organization is not None:
            queryset = queryset.filter(organization=organization)
        return queryset

    def _dashboard_pharmacy_queryset(self, user):
        queryset = Pharmacy.objects.select_related("organization")
        organization = self._admin_staff_organization(user)
        if organization is not None:
            queryset = queryset.filter(organization=organization)
        return queryset

    def _dashboard_pharmacist_queryset(self, user):
        queryset = PharmacistProfile.objects.select_related(
            "user",
            "pharmacy",
            "pharmacy__organization",
        )
        organization = self._admin_staff_organization(user)
        if organization is not None:
            queryset = queryset.filter(pharmacy__organization=organization)
        return queryset

    def _dashboard_prescription_queryset(self, user):
        queryset = Prescription.objects.select_related(
            "patient",
            "patient__organization",
        )
        organization = self._admin_staff_organization(user)
        if organization is not None:
            queryset = queryset.filter(patient__organization=organization)
        return queryset

    def _dashboard_sign_quality_queryset(self, user):
        queryset = SignQualityReport.objects.select_related(
            "patient",
            "patient__organization",
        )
        organization = self._admin_staff_organization(user)
        if organization is not None:
            queryset = queryset.filter(patient__organization=organization)
        return queryset

    def _dashboard_approval_queryset(self, user):
        roles = self._manageable_dashboard_roles(user)
        queryset = User.objects.filter(
            role__in=roles,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        organization = self._admin_staff_organization(user)
        if organization is not None:
            queryset = queryset.filter(
                patient_profile__organization=organization
            ) | queryset.filter(pharmacist_profile__pharmacy__organization=organization)
        return queryset.distinct()

    def _distribution(self, queryset, field_name):
        return [
            {"value": row[field_name] or "", "count": row["count"]}
            for row in queryset.values(field_name)
            .annotate(count=Count("id"))
            .order_by(field_name)
        ]

    def _hearing_condition_type_distribution(self, queryset):
        raw_counts = {
            row["hearing_condition_type"] or "": row["count"]
            for row in queryset.values("hearing_condition_type")
            .annotate(count=Count("id"))
            .order_by("hearing_condition_type")
        }
        distribution = [
            {
                "value": value,
                "label": str(label),
                "count": raw_counts.get(value, 0),
            }
            for value, label in HearingConditionTypeChoices.choices
        ]
        distribution.append(
            {
                "value": "",
                "label": "غير محدد",
                "count": raw_counts.get("", 0),
            }
        )
        return distribution

    def _age_group_distribution(self, queryset):
        today = timezone.localdate()
        groups = {
            "unknown": 0,
            "0-17": 0,
            "18-35": 0,
            "36-60": 0,
            "61+": 0,
        }
        for birth_date in queryset.values_list("birth_date", flat=True):
            if birth_date is None:
                groups["unknown"] += 1
                continue
            age = (
                today.year
                - birth_date.year
                - ((today.month, today.day) < (birth_date.month, birth_date.day))
            )
            if age < 18:
                groups["0-17"] += 1
            elif age <= 35:
                groups["18-35"] += 1
            elif age <= 60:
                groups["36-60"] += 1
            else:
                groups["61+"] += 1
        return [{"value": label, "count": count} for label, count in groups.items()]

    def _recent_patients_payload(self, queryset):
        return [
            {
                "id": patient.id,
                "full_name": patient.full_name,
                "phone_number": patient.phone_number or patient.user.phone_number or "",
                "gender": patient.gender,
                "hearing_disability_level": patient.hearing_disability_level,
                "qr_is_active": patient.qr_is_active,
                "created_at": patient.created_at,
            }
            for patient in queryset.order_by("-created_at")[:5]
        ]

    def _approval_request_name(self, user):
        if user.role == RoleChoices.PATIENT and hasattr(user, "patient_profile"):
            return user.patient_profile.full_name
        if user.role == RoleChoices.PHARMACIST and hasattr(user, "pharmacist_profile"):
            return user.pharmacist_profile.full_name
        return ""

    def _approval_request_queryset(self, request):
        queryset = User.objects.select_related(
            "patient_profile",
            "pharmacist_profile",
            "pharmacist_profile__pharmacy",
        ).filter(role__in=self._manageable_registration_roles(request.user))

        request_type = request.query_params.get("type")
        if request_type:
            queryset = queryset.filter(role=request_type)

        request_status = request.query_params.get("status")
        if request_status:
            queryset = queryset.filter(approval_status=request_status)

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(patient_profile__full_name__icontains=search)
                | Q(pharmacist_profile__full_name__icontains=search)
                | Q(pharmacist_profile__license_number__icontains=search)
            )
        return queryset.order_by("-created_at", "-id").distinct()

    def _serialize_approval_request(self, user, *, include_detail=True):
        return AdminApprovalRequestSerializer(
            user,
            context={"include_detail": include_detail},
        ).data

    def _get_manageable_approval_user_or_404(self, request, pk):
        user = get_object_or_404(
            User.objects.select_related(
                "patient_profile",
                "pharmacist_profile",
                "pharmacist_profile__pharmacy",
            ),
            pk=pk,
        )
        if not self._can_manage_user_role(request.user, user):
            return None, self._role_approval_denied()
        return user, None

    def _recent_approval_requests_payload(self, queryset):
        users = queryset.select_related(
            "patient_profile",
            "pharmacist_profile",
            "pharmacist_profile__pharmacy",
        ).order_by("-created_at")[:5]
        return [
            {
                "id": user.id,
                "name": self._approval_request_name(user),
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role,
                "approval_status": user.approval_status,
                "created_at": user.created_at,
            }
            for user in users
        ]

    def _dashboard_stats_payload(self, user):
        patient_queryset = self._dashboard_patient_queryset(user)
        pharmacist_queryset = self._dashboard_pharmacist_queryset(user)
        pharmacy_queryset = self._dashboard_pharmacy_queryset(user)
        prescription_queryset = self._dashboard_prescription_queryset(user)
        sign_quality_queryset = self._dashboard_sign_quality_queryset(user)
        approval_queryset = self._dashboard_approval_queryset(user)

        # City/region are not structured backend fields yet; keep this empty
        # until Phase B introduces an explicit location model/fields.
        patients_by_city = []

        return {
            "patients_count": patient_queryset.count(),
            "pharmacists_count": pharmacist_queryset.count(),
            "pharmacies_count": pharmacy_queryset.count(),
            "prescriptions_count": prescription_queryset.count(),
            "active_qr_count": patient_queryset.filter(qr_is_active=True).count(),
            "pending_approvals_count": approval_queryset.count(),
            "sign_quality_follow_up_count": sign_quality_queryset.filter(
                status__in=[
                    SignQualityReport.STATUS_OPEN,
                    SignQualityReport.STATUS_REVIEWED,
                ]
            ).count(),
            "gender_distribution": self._distribution(patient_queryset, "gender"),
            "hearing_severity_distribution": self._distribution(
                patient_queryset,
                "hearing_disability_level",
            ),
            "hearing_condition_type_distribution": (
                self._hearing_condition_type_distribution(patient_queryset)
            ),
            "age_groups": self._age_group_distribution(patient_queryset),
            "patients_by_city": patients_by_city,
            "recent_patients": self._recent_patients_payload(patient_queryset),
            "recent_approval_requests": self._recent_approval_requests_payload(
                approval_queryset
            ),
        }

    @action(detail=False, methods=["post"], url_path="pharmacist/register")
    def pharmacist_register(self, request):
        serializer = PharmacistRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = serializer.save()
        return Response(serializer.to_response(profile), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = serializer.validated_data["user"]
        blocked_response = self._approval_block_response(user)
        if blocked_response:
            return blocked_response
        return self._build_auth_response(user)

    @action(detail=False, methods=["post"], url_path="admin/auth/login")
    def admin_login(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = serializer.validated_data["user"]
        blocked_response = self._approval_block_response(user)
        if blocked_response:
            return blocked_response
        admin_response = self._ensure_admin_response(user)
        if admin_response:
            return admin_response
        return self._build_admin_auth_response(user)

    @action(detail=False, methods=["post"], url_path="patient/self-register")
    def patient_self_register(self, request):
        serializer = PatientSelfRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = serializer.save()
        return Response(serializer.to_response(user), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="patient/register")
    def patient_register(self, request):
        return self.patient_self_register(request)

    @action(detail=False, methods=["post"], url_path="patient/register/request-otp")
    def patient_register_request_otp(self, request):
        serializer = PatientRegistrationOTPRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response(serializer.save())
        except OTPDeliveryError as exc:
            return self._otp_delivery_failed_response(exc)
        except ValidationError as exc:
            return Response(
                validation_error_payload(exc.detail),
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"], url_path="pharmacist/register/request-otp")
    def pharmacist_register_request_otp(self, request):
        data = request.data.copy()
        data["role"] = "pharmacist"
        serializer = RegistrationOTPRequestSerializer(data=data)
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response(serializer.save())
        except OTPDeliveryError as exc:
            return self._otp_delivery_failed_response(exc)
        except ValidationError as exc:
            return Response(
                validation_error_payload(exc.detail),
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"], url_path="register/request-otp")
    def register_request_otp(self, request):
        serializer = RegistrationOTPRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response(serializer.save())
        except OTPDeliveryError as exc:
            return self._otp_delivery_failed_response(exc)
        except ValidationError as exc:
            return Response(
                validation_error_payload(exc.detail),
                status=status.HTTP_400_BAD_REQUEST,
            )

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

    @action(detail=False, methods=["get"], url_path="admin/approval-requests")
    def approval_requests(self, request):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        queryset = self._approval_request_queryset(request)
        paginator = AdminPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = AdminApprovalRequestSerializer(
            page,
            many=True,
            context={"include_detail": False},
        )
        return paginator.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"], url_path="admin/approval-requests")
    def approval_request_detail(self, request, pk=None):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        user, denied_response = self._get_manageable_approval_user_or_404(request, pk)
        if denied_response:
            return denied_response
        return Response(self._serialize_approval_request(user, include_detail=True))

    @action(detail=True, methods=["post"], url_path="admin/approval-requests/approve")
    def approve_approval_request(self, request, pk=None):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        user, denied_response = self._get_manageable_approval_user_or_404(request, pk)
        if denied_response:
            return denied_response
        user = self._approve_user_object(user, request.user)
        user.refresh_from_db()
        return Response(
            {
                "detail": "User approved successfully.",
                "request": self._serialize_approval_request(
                    user,
                    include_detail=True,
                ),
            }
        )

    @action(detail=True, methods=["post"], url_path="admin/approval-requests/reject")
    def reject_approval_request(self, request, pk=None):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        user, denied_response = self._get_manageable_approval_user_or_404(request, pk)
        if denied_response:
            return denied_response
        user = self._reject_user_object(user, request.data.get("reason", ""))
        user.refresh_from_db()
        return Response(
            {
                "detail": "User rejected successfully.",
                "request": self._serialize_approval_request(
                    user,
                    include_detail=True,
                ),
            }
        )

    @action(detail=True, methods=["post"], url_path="admin/users/approve")
    def approve_user(self, request, pk=None):
        if not self._can_manage_registration_requests(request.user):
            return self._registration_management_denied()
        user = get_object_or_404(User, pk=pk)
        if not self._can_manage_user_role(request.user, user):
            return self._role_approval_denied()
        self._approve_user_object(user, request.user)
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
        self._reject_user_object(user, request.data.get("reason", ""))
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
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError as exc:
            return error_response(
                "Invalid refresh token.",
                "invalid_refresh",
                fields={"refresh": str(exc)},
            )
        return Response({"detail": "Logged out successfully"})

    @action(detail=False, methods=["post"], url_path="admin/auth/logout")
    def admin_logout(self, request):
        return self.logout(request)

    @action(detail=False, methods=["post"], url_path="change-password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response({"detail": "Password changed successfully"})

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        return Response(AuthMeSerializer(request.user).data)

    @action(detail=False, methods=["get"], url_path="admin/auth/me")
    def admin_me(self, request):
        admin_response = self._ensure_admin_response(request.user)
        if admin_response:
            return admin_response
        return Response(AdminAuthMeSerializer(request.user).data)

    @action(detail=False, methods=["get"], url_path="admin/dashboard/stats")
    def admin_dashboard_stats(self, request):
        admin_response = self._ensure_admin_response(request.user)
        if admin_response:
            return admin_response
        return Response(self._dashboard_stats_payload(request.user))
