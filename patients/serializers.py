from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.crypto import get_random_string
from rest_framework import serializers

from accounts.serializers import (
    build_compat_patient_profile_payload,
    build_compat_user_payload,
)
from common.choices import BloodTypeChoices, RoleChoices
from .models import (
    PatientEnrollment,
    PatientLoginQR,
    PatientMedicalInfo,
    PatientProfile,
    PatientSession,
    PatientSessionQR,
    PatientSettings,
)
from .services import (
    assign_patient_qr_code,
    create_patient_account_from_enrollment,
    generate_patient_login_qr,
    generate_patient_session_qr,
    get_patient_session_qr_by_token,
    revoke_patient_login_qr,
)

User = get_user_model()


class PatientMedicalInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientMedicalInfo
        fields = (
            "blood_type",
            "chronic_conditions",
            "allergies",
            "is_pregnant",
            "is_breastfeeding",
            "notes",
            "updated_at",
        )
        read_only_fields = ("updated_at",)


class PatientProfileSerializer(serializers.ModelSerializer):
    medical_info = PatientMedicalInfoSerializer(read_only=True)
    enrollment_id = serializers.SerializerMethodField()

    class Meta:
        model = PatientProfile
        fields = (
            "id",
            "user",
            "organization",
            "enrollment_id",
            "full_name",
            "phone_number",
            "birth_date",
            "gender",
            "address",
            "hearing_disability_level",
            "is_self_registered",
            "qr_code_value",
            "qr_is_active",
            "created_at",
            "updated_at",
            "medical_info",
        )
        read_only_fields = (
            "id",
            "user",
            "qr_code_value",
            "qr_is_active",
            "created_at",
            "updated_at",
            "medical_info",
        )

    def get_enrollment_id(self, obj):
        enrollment = getattr(obj, "enrollment_record", None)
        return getattr(enrollment, "id", None)


class PatientSelfProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(max_length=255, required=False)
    phone = serializers.CharField(required=False, allow_blank=True)
    national_id = serializers.CharField(read_only=True)
    blood_type = serializers.ChoiceField(
        choices=BloodTypeChoices.choices,
        required=False,
        allow_blank=True,
    )
    allergies = serializers.CharField(required=False, allow_blank=True)
    chronic_conditions = serializers.CharField(required=False, allow_blank=True)
    regular_medications = serializers.CharField(required=False, allow_blank=True)
    is_pregnant = serializers.BooleanField(required=False, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field("gender").choices,
        required=False,
        allow_blank=True,
    )

    def to_representation(self, instance):
        medical_info, _ = PatientMedicalInfo.objects.get_or_create(patient=instance)
        return {
            "id": instance.id,
            "full_name": instance.full_name,
            "phone": instance.phone_number or instance.user.phone_number or "",
            "national_id": "",
            "blood_type": medical_info.blood_type,
            "allergies": medical_info.allergies,
            "chronic_conditions": medical_info.chronic_conditions,
            "regular_medications": medical_info.notes,
            "is_pregnant": medical_info.is_pregnant,
            "date_of_birth": instance.birth_date,
            "gender": instance.gender,
        }

    def update(self, instance, validated_data):
        profile_fields = []
        if "full_name" in validated_data:
            instance.full_name = validated_data["full_name"]
            profile_fields.append("full_name")
        if "phone" in validated_data:
            instance.phone_number = validated_data["phone"]
            instance.user.phone_number = validated_data["phone"]
            instance.user.save(update_fields=["phone_number", "updated_at"])
            profile_fields.append("phone_number")
        if "date_of_birth" in validated_data:
            instance.birth_date = validated_data["date_of_birth"]
            profile_fields.append("birth_date")
        if "gender" in validated_data:
            instance.gender = validated_data["gender"]
            profile_fields.append("gender")
        if profile_fields:
            profile_fields.append("updated_at")
            instance.save(update_fields=profile_fields)

        medical_info, _ = PatientMedicalInfo.objects.get_or_create(patient=instance)
        medical_fields = []
        if "blood_type" in validated_data:
            medical_info.blood_type = validated_data["blood_type"]
            medical_fields.append("blood_type")
        if "allergies" in validated_data:
            medical_info.allergies = validated_data["allergies"]
            medical_fields.append("allergies")
        if "chronic_conditions" in validated_data:
            medical_info.chronic_conditions = validated_data["chronic_conditions"]
            medical_fields.append("chronic_conditions")
        if "regular_medications" in validated_data:
            medical_info.notes = validated_data["regular_medications"]
            medical_fields.append("notes")
        if "is_pregnant" in validated_data:
            medical_info.is_pregnant = validated_data["is_pregnant"]
            medical_fields.append("is_pregnant")
        if medical_fields:
            medical_fields.append("updated_at")
            medical_info.save(update_fields=medical_fields)
        return instance


class PatientSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientSettings
        fields = (
            "notifications_enabled",
            "prescription_reminders",
            "dark_mode",
            "use_biometrics",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


class AdminPatientCreateAccountSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    full_name = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        min_length=8,
    )
    national_id = serializers.CharField(required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field("gender").choices,
        required=False,
        allow_blank=True,
    )
    blood_type = serializers.ChoiceField(
        choices=BloodTypeChoices.choices,
        required=False,
        allow_blank=True,
    )
    allergies = serializers.CharField(required=False, allow_blank=True)
    chronic_conditions = serializers.CharField(required=False, allow_blank=True)
    regular_medications = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        if password:
            validate_password(password)
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        password = validated_data.get("password")
        temporary_password_generated = False
        if not password:
            password = get_random_string(16)
            temporary_password_generated = True

        staff_profile = getattr(request.user, "organization_staff_profile", None)
        organization = (
            None
            if request.user.is_superuser
            else getattr(
                staff_profile,
                "organization",
                None,
            )
        )
        user = User.objects.create_user(
            email=validated_data.get("email") or None,
            password=password,
            phone_number=validated_data["phone_number"],
            role=RoleChoices.PATIENT,
            is_active=True,
            is_verified=True,
        )
        patient = PatientProfile.objects.create(
            user=user,
            organization=organization,
            full_name=validated_data["full_name"],
            phone_number=validated_data["phone_number"],
            birth_date=validated_data.get("date_of_birth"),
            gender=validated_data.get("gender", ""),
            is_self_registered=False,
        )
        PatientMedicalInfo.objects.create(
            patient=patient,
            blood_type=validated_data.get("blood_type", ""),
            allergies=validated_data.get("allergies", ""),
            chronic_conditions=validated_data.get("chronic_conditions", ""),
            notes=validated_data.get("regular_medications")
            or validated_data.get("notes", ""),
        )
        return {
            "user": user,
            "patient": patient,
            "temporary_password_generated": temporary_password_generated,
            "temporary_password": password if temporary_password_generated else None,
        }

    def to_response(self, result):
        profile = build_compat_patient_profile_payload(result["patient"])
        profile["national_id"] = self.validated_data.get("national_id", "")
        profile["blood_type"] = self.validated_data.get("blood_type", "")
        payload = {
            "user": build_compat_user_payload(result["user"]),
            "profile": profile,
            "temporary_password_generated": result["temporary_password_generated"],
        }
        if result["temporary_password_generated"]:
            payload["temporary_password"] = result["temporary_password"]
        return payload


class PatientLoginQRSerializer(serializers.ModelSerializer):
    patient_id = serializers.IntegerField(source="patient.id", read_only=True)

    class Meta:
        model = PatientLoginQR
        fields = (
            "patient_id",
            "is_active",
            "created_at",
            "revoked_at",
        )
        read_only_fields = fields


class GeneratePatientLoginQRSerializer(serializers.Serializer):
    def save(self, **kwargs):
        patient = self.context["patient"]
        created_by = self.context["request"].user
        token, login_qr = generate_patient_login_qr(patient, created_by=created_by)
        return {
            "patient_id": patient.id,
            "qr_token": token,
            "qr_payload": token,
            "is_active": login_qr.is_active,
            "created_at": login_qr.created_at,
            "revoked_at": login_qr.revoked_at,
        }


class RevokePatientLoginQRSerializer(serializers.Serializer):
    def save(self, **kwargs):
        patient = self.context["patient"]
        revoke_patient_login_qr(patient)
        return {"patient_id": patient.id, "is_active": False}


class GeneratePatientSessionQRSerializer(serializers.Serializer):
    def save(self, **kwargs):
        patient = self.context["patient"]
        token, session_qr, expires_in_seconds = generate_patient_session_qr(patient)
        return {
            "qr_token": token,
            "qr_payload": token,
            "expires_at": session_qr.expires_at,
            "expires_in_seconds": expires_in_seconds,
        }


class StartPatientSessionByQRSerializer(serializers.Serializer):
    qr_token = serializers.CharField(required=False)
    qr_payload = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        token = attrs.get("qr_token") or attrs.get("qr_payload")
        if not token:
            raise serializers.ValidationError({"qr_token": ["This field is required."]})
        session_qr = get_patient_session_qr_by_token(token)
        if not session_qr:
            raise serializers.ValidationError({"detail": "Invalid QR token."})
        if session_qr.revoked_at:
            raise serializers.ValidationError(
                {"detail": "This QR token has been revoked."}
            )
        if session_qr.used_at:
            raise serializers.ValidationError(
                {"detail": "This QR token has already been used."}
            )
        if session_qr.is_expired:
            raise serializers.ValidationError({"detail": "QR token has expired."})
        if not session_qr.patient.user.is_active:
            raise serializers.ValidationError(
                {"detail": "This patient account is inactive."}
            )
        attrs["session_qr"] = session_qr
        return attrs


def build_session_patient_payload(patient):
    return {
        "id": patient.id,
        "full_name": patient.full_name,
        "phone_number": patient.phone_number or patient.user.phone_number or "",
        "gender": patient.get_gender_display().lower() if patient.gender else "",
        "birth_date": patient.birth_date,
    }


def build_session_medical_info_payload(patient):
    medical_info = getattr(patient, "medical_info", None)
    return {
        "blood_type": getattr(medical_info, "blood_type", ""),
        "allergies": getattr(medical_info, "allergies", ""),
        "chronic_conditions": getattr(medical_info, "chronic_conditions", ""),
        "regular_medications": getattr(medical_info, "notes", ""),
        "is_pregnant": getattr(medical_info, "is_pregnant", False) or False,
        "is_breastfeeding": getattr(medical_info, "is_breastfeeding", False) or False,
    }


def build_recent_prescription_item_payload(item):
    return {
        "id": item.id,
        "medicine_name": item.medicine_name,
        "dosage": item.dosage,
        "frequency": item.frequency,
        "duration": item.duration,
        "instructions_text": item.instructions_text,
        "sign_status": item.sign_status,
    }


def build_recent_prescription_payload(prescription):
    return {
        "id": prescription.id,
        "status": prescription.status,
        "doctor_name": prescription.doctor_name,
        "diagnosis": prescription.diagnosis,
        "notes": prescription.notes,
        "submitted_at": prescription.submitted_at,
        "items": [
            build_recent_prescription_item_payload(item)
            for item in prescription.items.all()
        ],
    }


def build_recent_prescriptions_payload(patient):
    from common.choices import PrescriptionStatusChoices
    from prescriptions.models import Prescription

    prescriptions = (
        Prescription.objects.prefetch_related("items")
        .filter(
            patient=patient,
            status=PrescriptionStatusChoices.SUBMITTED,
            submitted_at__isnull=False,
        )
        .order_by("-submitted_at", "-created_at")[:3]
    )
    return [
        build_recent_prescription_payload(prescription)
        for prescription in prescriptions
    ]


def build_session_response_payload(session):
    return {
        "session": {
            "id": session.id,
            "status": session.status,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
        },
        "patient": build_session_patient_payload(session.patient),
        "medical_info": build_session_medical_info_payload(session.patient),
        "recent_prescriptions": build_recent_prescriptions_payload(session.patient),
        "pharmacist": {
            "id": session.pharmacist.id,
            "full_name": session.pharmacist.full_name,
        },
        "pharmacy": {
            "id": session.pharmacy.id,
            "name": session.pharmacy.name,
        },
    }


class PharmacistPatientSessionSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    pharmacist = serializers.SerializerMethodField()
    pharmacy = serializers.SerializerMethodField()

    class Meta:
        model = PatientSession
        fields = (
            "id",
            "status",
            "started_at",
            "ended_at",
            "expires_at",
            "created_at",
            "patient",
            "pharmacist",
            "pharmacy",
        )
        read_only_fields = fields

    def get_patient(self, obj):
        return build_session_patient_payload(obj.patient)

    def get_pharmacist(self, obj):
        return {"id": obj.pharmacist.id, "full_name": obj.pharmacist.full_name}

    def get_pharmacy(self, obj):
        return {"id": obj.pharmacy.id, "name": obj.pharmacy.name}


class PatientEnrollmentSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    patient_profile_id = serializers.IntegerField(
        source="patient_profile.id",
        read_only=True,
    )
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = PatientEnrollment
        fields = (
            "id",
            "organization",
            "organization_name",
            "patient_profile_id",
            "join_date",
            "first_name",
            "last_name",
            "father_name",
            "mother_name",
            "birth_date",
            "gender",
            "address",
            "phone_number",
            "hearing_disability_level",
            "notes",
            "is_account_created",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "patient_profile_id",
            "is_account_created",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        )

    def validate_organization(self, value):
        request = self.context["request"]
        staff_organization = getattr(
            getattr(request.user, "organization_staff_profile", None),
            "organization",
            None,
        )
        if request.user.is_superuser or staff_organization is None:
            return value
        if value != staff_organization:
            raise serializers.ValidationError(
                "You can only manage enrollments inside your organization."
            )
        return value


class CreatePatientAccountSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    record_access_pin = serializers.CharField(
        required=False,
        allow_blank=False,
        write_only=True,
        min_length=4,
        max_length=12,
    )

    def validate_email(self, value):
        from accounts.models import User

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def save(self, **kwargs):
        enrollment = self.context["enrollment"]
        profile = create_patient_account_from_enrollment(
            enrollment,
            email=self.validated_data["email"],
            password=self.validated_data["password"],
            phone_number=self.validated_data.get("phone_number", ""),
            record_access_pin=self.validated_data.get("record_access_pin"),
        )
        return profile


class GeneratePatientQRSerializer(serializers.Serializer):
    regenerate = serializers.BooleanField(default=False)

    def save(self, **kwargs):
        patient = self.context["patient"]
        qr_code_value = assign_patient_qr_code(
            patient,
            regenerate=self.validated_data.get("regenerate", False),
        )
        return {"qr_code_value": qr_code_value, "qr_is_active": patient.qr_is_active}


class StartPatientSessionSerializer(serializers.Serializer):
    qr_code_value = serializers.CharField()


class PatientSessionSerializer(serializers.ModelSerializer):
    patient_id = serializers.IntegerField(source="patient.id", read_only=True)
    pharmacist_id = serializers.IntegerField(source="pharmacist.id", read_only=True)
    pharmacy_id = serializers.IntegerField(source="pharmacy.id", read_only=True)

    class Meta:
        model = PatientSession
        fields = (
            "id",
            "patient_id",
            "pharmacist_id",
            "pharmacy_id",
            "access_type",
            "qr_code_value_snapshot",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
