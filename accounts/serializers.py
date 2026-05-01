import logging
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from common.choices import RoleChoices
from common.utils import verify_pin
from patients.models import PatientMedicalInfo, PatientProfile
from patients.services import assign_patient_qr_code, get_patient_by_login_qr_token
from .models import PhoneOTP

User = get_user_model()
logger = logging.getLogger(__name__)

OTP_EXPIRY_SECONDS = 300


def build_compat_user_payload(user):
    return {
        "id": user.id,
        "email": user.email,
        "phone_number": user.phone_number or "",
        "role": user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
    }


def build_compat_patient_profile_payload(profile):
    medical_info = getattr(profile, "medical_info", None)
    return {
        "id": profile.id,
        "full_name": profile.full_name,
        "national_id": "",
        "blood_type": "",
        "allergies": getattr(medical_info, "allergies", ""),
        "chronic_conditions": getattr(medical_info, "chronic_conditions", ""),
        "regular_medications": getattr(medical_info, "notes", ""),
        "is_pregnant": getattr(medical_info, "is_pregnant", False) or False,
    }


def build_compat_pharmacy_payload(pharmacy):
    return {
        "id": pharmacy.id,
        "name": pharmacy.name,
        "address": pharmacy.address,
        "phone": pharmacy.phone_number,
        "lat": pharmacy.latitude,
        "lng": pharmacy.longitude,
        "has_sign_service": True,
    }


def build_compat_pharmacist_profile_payload(profile):
    return {
        "id": profile.id,
        "full_name": profile.full_name,
        "license_number": profile.license_number,
        "is_approved": profile.is_approved,
        "pharmacy": build_compat_pharmacy_payload(profile.pharmacy),
    }


class UserSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "phone_number",
            "role",
            "is_active",
            "is_verified",
            "created_at",
            "updated_at",
            "profile",
        )
        read_only_fields = ("id", "created_at", "updated_at", "profile")

    def get_profile(self, obj):
        if hasattr(obj, "patient_profile"):
            profile = obj.patient_profile
            return {
                "patient_id": profile.id,
                "full_name": profile.full_name,
                "qr_is_active": profile.qr_is_active,
            }
        if hasattr(obj, "pharmacist_profile"):
            profile = obj.pharmacist_profile
            return {
                "pharmacist_id": profile.id,
                "full_name": profile.full_name,
                "pharmacy_id": profile.pharmacy_id,
                "is_approved": profile.is_approved,
            }
        if hasattr(obj, "organization_staff_profile"):
            profile = obj.organization_staff_profile
            return {
                "organization_staff_profile_id": profile.id,
                "organization_id": profile.organization_id,
                "can_manage_patients": profile.can_manage_patients,
                "can_manage_pharmacists": profile.can_manage_pharmacists,
            }
        return None


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    password = serializers.CharField()

    def validate(self, attrs):
        email = attrs.get("email")
        phone_number = attrs.get("phone_number") or attrs.get("phone")
        if not email and not phone_number:
            raise serializers.ValidationError(
                {"detail": "Email or phone number is required."}
            )

        user = None
        if phone_number:
            user = User.objects.filter(phone_number=phone_number).first()
        elif email:
            user = User.objects.filter(email__iexact=email).first()

        if not user or not user.check_password(attrs["password"]):
            raise serializers.ValidationError({"detail": "Invalid credentials."})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "This account is inactive."})
        attrs["user"] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class PatientRegistrationOTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        phone_number = attrs.get("phone_number") or attrs.get("phone")
        if not phone_number:
            raise serializers.ValidationError(
                {"detail": "Phone number is required."}
            )
        if User.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError(
                {"detail": "Phone number is already registered."}
            )
        attrs["phone_number"] = phone_number
        return attrs

    def save(self, **kwargs):
        phone_number = self.validated_data["phone_number"]
        purpose = PhoneOTP.PURPOSE_PATIENT_REGISTER
        PhoneOTP.objects.filter(
            phone_number=phone_number,
            purpose=purpose,
            used_at__isnull=True,
        ).update(used_at=timezone.now())

        otp = f"{random.SystemRandom().randint(0, 999999):06d}"
        challenge = PhoneOTP(
            phone_number=phone_number,
            purpose=purpose,
            expires_at=timezone.now() + timezone.timedelta(seconds=OTP_EXPIRY_SECONDS),
        )
        challenge.set_code(otp)
        challenge.save()

        if settings.DEBUG:
            logger.warning(
                "Development OTP for %s (%s): %s",
                phone_number,
                purpose,
                otp,
            )

        payload = {
            "detail": "Registration OTP generated successfully.",
            "expires_in_seconds": OTP_EXPIRY_SECONDS,
        }
        if settings.DEBUG:
            payload["debug_otp"] = otp
        return payload


def validate_patient_registration_otp(phone_number, otp):
    challenge = (
        PhoneOTP.objects.filter(
            phone_number=phone_number,
            purpose=PhoneOTP.PURPOSE_PATIENT_REGISTER,
            used_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if not challenge:
        raise serializers.ValidationError({"detail": "Invalid OTP."})
    if challenge.attempts >= challenge.max_attempts:
        challenge.mark_used()
        raise serializers.ValidationError({"detail": "Too many OTP attempts."})
    if challenge.is_expired:
        challenge.mark_used()
        raise serializers.ValidationError({"detail": "OTP has expired."})
    if not challenge.check_code(otp):
        challenge.attempts += 1
        update_fields = ["attempts", "updated_at"]
        if challenge.attempts >= challenge.max_attempts:
            challenge.used_at = timezone.now()
            update_fields.append("used_at")
        challenge.save(update_fields=update_fields)
        if challenge.attempts >= challenge.max_attempts:
            raise serializers.ValidationError({"detail": "Too many OTP attempts."})
        raise serializers.ValidationError({"detail": "Invalid OTP."})
    challenge.mark_used()
    return challenge


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Current password is incorrect."))
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": _("New password and confirmation do not match.")}
            )
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class AuthMeSerializer(serializers.Serializer):
    def to_representation(self, user):
        profile = None
        if user.role == RoleChoices.PATIENT and hasattr(user, "patient_profile"):
            profile = build_compat_patient_profile_payload(user.patient_profile)
        elif user.role == RoleChoices.PHARMACIST and hasattr(
            user, "pharmacist_profile"
        ):
            profile = build_compat_pharmacist_profile_payload(user.pharmacist_profile)

        return {
            "user": build_compat_user_payload(user),
            "profile": profile,
        }


class PatientQRLoginSerializer(serializers.Serializer):
    qr_token = serializers.CharField(required=False)
    qr_code_value = serializers.CharField(required=False, write_only=True)
    pin = serializers.CharField(
        required=False,
        write_only=True,
        min_length=4,
        max_length=12,
    )

    def validate(self, attrs):
        token = attrs.get("qr_token")
        if token:
            login_qr = get_patient_by_login_qr_token(token)
            if not login_qr:
                raise serializers.ValidationError({"detail": "Invalid QR token."})
            if not login_qr.is_active or login_qr.revoked_at:
                raise serializers.ValidationError(
                    {"detail": "QR token has been revoked."}
                )
            patient_profile = login_qr.patient
            user = patient_profile.user
            if user.role != RoleChoices.PATIENT:
                raise serializers.ValidationError(
                    {"detail": "QR token is not linked to a patient account."}
                )
            if not user.is_active:
                raise serializers.ValidationError(
                    {"detail": "This patient account is inactive."}
                )
            attrs["user"] = user
            attrs["patient_profile"] = patient_profile
            return attrs

        if attrs.get("qr_code_value") and attrs.get("pin"):
            try:
                patient_profile = PatientProfile.objects.select_related("user").get(
                    qr_code_value=attrs["qr_code_value"],
                    qr_is_active=True,
                )
            except PatientProfile.DoesNotExist:
                raise serializers.ValidationError({"detail": "Invalid QR code or PIN."})

            user = patient_profile.user
            if user.role != RoleChoices.PATIENT or not user.is_active:
                raise serializers.ValidationError({"detail": "Invalid QR code or PIN."})

            if not verify_pin(attrs["pin"], patient_profile.record_access_pin_hash):
                raise serializers.ValidationError({"detail": "Invalid QR code or PIN."})

            attrs["user"] = user
            attrs["patient_profile"] = patient_profile
            return attrs

        raise serializers.ValidationError({"detail": "QR token is required."})


class PatientSelfRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        min_length=8,
    )
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)
    confirm_password = serializers.CharField(
        required=False,
        write_only=True,
        min_length=8,
    )
    full_name = serializers.CharField(max_length=255, required=False)
    name = serializers.CharField(max_length=255, required=False, write_only=True)
    national_id = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field("gender").choices,
        required=False,
        allow_blank=True,
    )
    address = serializers.CharField(required=False, allow_blank=True)
    hearing_disability_level = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field("hearing_disability_level").choices,
        required=False,
        allow_blank=True,
    )
    record_access_pin = serializers.CharField(
        required=False,
        allow_blank=False,
        min_length=4,
        max_length=12,
        write_only=True,
    )

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        full_name = attrs.get("full_name") or attrs.get("name")
        phone_number = attrs.get("phone_number") or attrs.get("phone")
        if not full_name:
            raise serializers.ValidationError({"full_name": "This field is required."})
        if not phone_number:
            raise serializers.ValidationError(
                {"phone_number": "This field is required."}
            )
        if User.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError(
                {"phone_number": "A user with this phone number already exists."}
            )
        if (
            attrs.get("confirm_password")
            and attrs["password"] != attrs["confirm_password"]
        ):
            raise serializers.ValidationError(
                {"confirm_password": "Password and confirmation do not match."}
            )
        validate_patient_registration_otp(phone_number, attrs["otp"])
        attrs["full_name"] = full_name
        attrs["phone_number"] = phone_number
        return attrs

    def create(self, validated_data):
        validated_data.pop("phone", None)
        validated_data.pop("name", None)
        validated_data.pop("national_id", None)
        validated_data.pop("confirm_password", None)
        validated_data.pop("otp", None)
        user = User.objects.create_user(
            email=validated_data.get("email") or None,
            password=validated_data["password"],
            phone_number=validated_data.get("phone_number", ""),
            role=RoleChoices.PATIENT,
            is_active=True,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name=validated_data["full_name"],
            phone_number=validated_data.get("phone_number", ""),
            birth_date=validated_data.get("birth_date"),
            gender=validated_data.get("gender", ""),
            address=validated_data.get("address", ""),
            hearing_disability_level=validated_data.get("hearing_disability_level", ""),
            is_self_registered=True,
        )
        if validated_data.get("record_access_pin"):
            profile.set_record_access_pin(validated_data["record_access_pin"])
            profile.save(update_fields=["record_access_pin_hash", "updated_at"])
        PatientMedicalInfo.objects.get_or_create(patient=profile)
        assign_patient_qr_code(profile)
        return user
