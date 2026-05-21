from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import serializers

from accounts.models import PhoneOTP
from accounts.serializers import (
    REGISTRATION_PENDING_DETAIL,
    build_compat_pharmacist_profile_payload,
    build_compat_user_payload,
)
from accounts.services import validate_registration_otp
from common.choices import ApprovalStatusChoices, RoleChoices

from .models import PharmacistProfile, Pharmacy

User = get_user_model()


class PharmacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = (
            "id",
            "name",
            "owner_user",
            "address",
            "city",
            "region",
            "latitude",
            "longitude",
            "is_contracted_with_organization",
            "organization",
            "phone_number",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        request = self.context["request"]
        staff_organization = getattr(
            getattr(request.user, "organization_staff_profile", None),
            "organization",
            None,
        )
        organization = attrs.get("organization")
        if (
            request.user.is_superuser
            or staff_organization is None
            or organization is None
        ):
            return attrs
        if organization != staff_organization:
            raise serializers.ValidationError(
                "You can only manage pharmacies within your organization."
            )
        return attrs


class AdminPharmacySerializer(serializers.ModelSerializer):
    pharmacists_count = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()

    class Meta:
        model = Pharmacy
        fields = (
            "id",
            "name",
            "phone_number",
            "city",
            "region",
            "address",
            "license_number",
            "pharmacists_count",
            "status",
            "created_at",
            "updated_at",
            "notes",
            "latitude",
            "longitude",
            "is_contracted_with_organization",
            "organization",
        )
        read_only_fields = fields

    def get_pharmacists_count(self, obj):
        if hasattr(obj, "pharmacists_count"):
            return obj.pharmacists_count
        return obj.pharmacists.count()

    def get_status(self, obj):
        return None

    def get_notes(self, obj):
        return None

    def get_organization(self, obj):
        if obj.organization_id is None:
            return None
        return {
            "id": obj.organization_id,
            "name": obj.organization.name,
        }


class AdminPharmacyWriteSerializer(serializers.ModelSerializer):
    ADMIN_ORGANIZATION_REQUIRED_DETAIL = (
        "Contracted pharmacies require an organization-linked admin account or an "
        "explicit organization."
    )

    class Meta:
        model = Pharmacy
        fields = (
            "name",
            "phone_number",
            "address",
            "city",
            "region",
            "license_number",
            "latitude",
            "longitude",
            "is_contracted_with_organization",
            "organization",
        )

    def validate(self, attrs):
        request = self.context["request"]
        staff_organization = getattr(
            getattr(request.user, "organization_staff_profile", None),
            "organization",
            None,
        )
        submitted_organization = attrs.get("organization")
        organization = attrs.get(
            "organization",
            getattr(self.instance, "organization", None),
        )
        is_contracted = attrs.get(
            "is_contracted_with_organization",
            getattr(self.instance, "is_contracted_with_organization", False),
        )

        if staff_organization is not None:
            if (
                submitted_organization is not None
                and submitted_organization != staff_organization
            ):
                raise serializers.ValidationError(
                    {
                        "detail": "You can only manage pharmacies within your organization.",
                        "code": "organization_scope_mismatch",
                        "fields": {
                            "organization": (
                                "Organization staff cannot assign pharmacies to a "
                                "different organization."
                            )
                        },
                    }
                )
            if organization is not None and organization != staff_organization:
                raise serializers.ValidationError(
                    {
                        "detail": "You can only manage pharmacies within your organization.",
                        "code": "organization_scope_mismatch",
                        "fields": {
                            "organization": (
                                "This pharmacy belongs to a different organization."
                            )
                        },
                    }
                )
            if is_contracted:
                attrs["organization"] = staff_organization
                organization = staff_organization

        if is_contracted and organization is None:
            raise serializers.ValidationError(
                {
                    "detail": self.ADMIN_ORGANIZATION_REQUIRED_DETAIL,
                    "code": "admin_organization_required",
                    "fields": {
                        "organization": self.ADMIN_ORGANIZATION_REQUIRED_DETAIL,
                    },
                }
            )
        return attrs


class PharmacyCompatSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(max_length=255, required=False)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    region = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    lat = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    lng = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    has_sign_service = serializers.BooleanField(required=False, default=True)

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "name": instance.name,
            "address": instance.address,
            "city": instance.city,
            "region": instance.region,
            "phone": instance.phone_number,
            "lat": instance.latitude,
            "lng": instance.longitude,
            "has_sign_service": True,
        }

    def update(self, instance, validated_data):
        field_map = {
            "name": "name",
            "address": "address",
            "city": "city",
            "region": "region",
            "phone": "phone_number",
            "lat": "latitude",
            "lng": "longitude",
        }
        changed_fields = []
        for serializer_field, model_field in field_map.items():
            if serializer_field in validated_data:
                setattr(instance, model_field, validated_data[serializer_field])
                changed_fields.append(model_field)
        if changed_fields:
            changed_fields.append("updated_at")
            instance.save(update_fields=changed_fields)
        return instance


class SafePharmacySerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)

    class Meta:
        model = Pharmacy
        fields = (
            "id",
            "name",
            "city",
            "region",
            "address",
            "phone_number",
            "latitude",
            "longitude",
            "is_contracted_with_organization",
        )
        read_only_fields = fields


class PharmacistProfileSerializer(serializers.ModelSerializer):
    pharmacy = PharmacySerializer(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)

    class Meta:
        model = PharmacistProfile
        fields = (
            "id",
            "email",
            "phone_number",
            "pharmacy",
            "full_name",
            "license_number",
            "is_approved",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "is_approved", "created_at", "updated_at")


class AdminPharmacistSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    pharmacy_id = serializers.IntegerField(source="pharmacy.id", read_only=True)
    pharmacy = serializers.SerializerMethodField()
    account_status = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()

    class Meta:
        model = PharmacistProfile
        fields = (
            "id",
            "user_id",
            "full_name",
            "phone_number",
            "email",
            "license_number",
            "pharmacy_id",
            "pharmacy",
            "account_status",
            "is_approved",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_pharmacy(self, obj):
        return {
            "id": obj.pharmacy_id,
            "name": obj.pharmacy.name,
            "city": None,
            "region": None,
            "address": obj.pharmacy.address,
        }

    def get_account_status(self, obj):
        return {
            "is_active": obj.user.is_active,
            "approval_status": obj.user.approval_status,
            "is_verified": obj.user.is_verified,
        }

    def get_notes(self, obj):
        return None


class AdminPharmacistWriteSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        min_length=8,
    )
    full_name = serializers.CharField(max_length=255, required=False)
    license_number = serializers.CharField(required=False, allow_blank=True)
    pharmacy_id = serializers.IntegerField(required=False)
    is_approved = serializers.BooleanField(required=False)
    account_status = serializers.DictField(required=False)
    user = serializers.DictField(required=False)

    def validate_email(self, value):
        pharmacist = self.instance
        queryset = (
            User.objects.filter(email__iexact=value) if value else User.objects.none()
        )
        if pharmacist is not None:
            queryset = queryset.exclude(pk=pharmacist.user_id)
        if queryset.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone_number(self, value):
        pharmacist = self.instance
        queryset = (
            User.objects.filter(phone_number=value) if value else User.objects.none()
        )
        if pharmacist is not None:
            queryset = queryset.exclude(pk=pharmacist.user_id)
        if queryset.exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )
        return value

    def validate_license_number(self, value):
        pharmacist = self.instance
        queryset = PharmacistProfile.objects.filter(license_number__iexact=value)
        if pharmacist is not None:
            queryset = queryset.exclude(pk=pharmacist.pk)
        if value and queryset.exists():
            raise serializers.ValidationError(
                "A pharmacist with this license number already exists."
            )
        return value

    def validate(self, attrs):
        creating = self.instance is None
        if creating:
            required = {}
            for field in ("full_name", "license_number", "pharmacy_id"):
                if not attrs.get(field):
                    required[field] = "This field is required."
            if not attrs.get("phone_number") and not attrs.get("email"):
                required["phone_number"] = "Phone number or email is required."
            if required:
                raise serializers.ValidationError(required)
            password = attrs.get("password")
            if password:
                validate_password(password)

        request = self.context["request"]
        pharmacy_id = attrs.get("pharmacy_id")
        if pharmacy_id is not None:
            try:
                pharmacy = Pharmacy.objects.get(pk=pharmacy_id)
            except Pharmacy.DoesNotExist:
                raise serializers.ValidationError({"pharmacy_id": "Invalid pharmacy."})
            staff_organization = getattr(
                getattr(request.user, "organization_staff_profile", None),
                "organization",
                None,
            )
            if (
                staff_organization is not None
                and not request.user.is_superuser
                and pharmacy.organization_id != staff_organization.id
            ):
                raise serializers.ValidationError(
                    {
                        "pharmacy_id": (
                            "You can only assign pharmacists to pharmacies within "
                            "your organization."
                        )
                    }
                )
            attrs["pharmacy"] = pharmacy

        for status_container in ("account_status", "user"):
            values = attrs.get(status_container) or {}
            approval_status = values.get("approval_status")
            if approval_status and approval_status not in ApprovalStatusChoices.values:
                raise serializers.ValidationError(
                    {status_container: {"approval_status": "Invalid approval status."}}
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        pharmacy = validated_data.pop("pharmacy")
        validated_data.pop("pharmacy_id", None)
        account_status = validated_data.pop("account_status", {}) or {}
        user_data = validated_data.pop("user", {}) or {}
        approval_status = (
            user_data.get("approval_status")
            or account_status.get("approval_status")
            or ApprovalStatusChoices.APPROVED
        )
        is_approved = validated_data.pop(
            "is_approved",
            approval_status == ApprovalStatusChoices.APPROVED,
        )
        supplied_password = bool(validated_data.get("password"))
        password = validated_data.pop("password", "") or get_random_string(16)
        temporary_password_generated = not supplied_password

        user = User.objects.create_user(
            email=validated_data.get("email") or None,
            password=password,
            phone_number=validated_data.get("phone_number", ""),
            role=RoleChoices.PHARMACIST,
            is_active=bool(
                user_data.get("is_active", account_status.get("is_active", True))
            ),
            is_verified=approval_status == ApprovalStatusChoices.APPROVED,
            approval_status=approval_status,
        )
        if approval_status == ApprovalStatusChoices.APPROVED:
            user.approved_at = timezone.now()
            user.approved_by = request.user
            user.save(update_fields=["approved_at", "approved_by", "updated_at"])

        profile = PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name=validated_data["full_name"],
            license_number=validated_data.get("license_number", ""),
            is_approved=bool(is_approved),
        )
        self.temporary_password_generated = temporary_password_generated
        self.temporary_password = password if temporary_password_generated else None
        return profile

    @transaction.atomic
    def update(self, instance, validated_data):
        pharmacy = validated_data.pop("pharmacy", None)
        validated_data.pop("pharmacy_id", None)
        account_status = validated_data.pop("account_status", {}) or {}
        user_data = validated_data.pop("user", {}) or {}

        profile_fields = []
        for field in ("full_name", "license_number", "is_approved"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
                profile_fields.append(field)
        if pharmacy is not None:
            instance.pharmacy = pharmacy
            profile_fields.append("pharmacy")

        user = instance.user
        user_fields = []
        for field in ("email", "phone_number"):
            if field in validated_data:
                setattr(user, field, validated_data[field] or None)
                user_fields.append(field)

        status_payload = {}
        status_payload.update(user_data)
        status_payload.update(account_status)
        if "is_active" in status_payload:
            user.is_active = bool(status_payload["is_active"])
            user_fields.append("is_active")
        if "approval_status" in status_payload:
            user.approval_status = status_payload["approval_status"]
            user_fields.append("approval_status")
            if user.approval_status == ApprovalStatusChoices.APPROVED:
                user.is_verified = True
                user.approved_at = timezone.now()
                user.approved_by = self.context["request"].user
                user.rejection_reason = ""
                instance.is_approved = True
                user_fields.extend(
                    ["is_verified", "approved_at", "approved_by", "rejection_reason"]
                )
                if "is_approved" not in profile_fields:
                    profile_fields.append("is_approved")
            elif user.approval_status == ApprovalStatusChoices.REJECTED:
                user.is_verified = False
                instance.is_approved = False
                user_fields.append("is_verified")
                if "is_approved" not in profile_fields:
                    profile_fields.append("is_approved")

        if "is_approved" in validated_data:
            if instance.is_approved:
                user.approval_status = ApprovalStatusChoices.APPROVED
                user.is_verified = True
                user_fields.extend(["approval_status", "is_verified"])
            else:
                user.approval_status = ApprovalStatusChoices.PENDING
                user.is_verified = False
                user_fields.extend(["approval_status", "is_verified"])

        if user_fields:
            user_fields.append("updated_at")
            user.save(update_fields=list(dict.fromkeys(user_fields)))
        if profile_fields:
            profile_fields.append("updated_at")
            instance.save(update_fields=list(dict.fromkeys(profile_fields)))
        instance.refresh_from_db()
        return instance


class PharmacistRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        min_length=8,
    )
    confirm_password = serializers.CharField(
        required=False,
        write_only=True,
        min_length=8,
    )
    full_name = serializers.CharField(max_length=255, required=False)
    name = serializers.CharField(max_length=255, required=False, write_only=True)
    pharmacy_id = serializers.IntegerField(required=False, write_only=True)
    pharmacy_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    pharmacy_address = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    pharmacy_phone_number = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    license_number = serializers.CharField(required=False, allow_blank=True)
    license_id = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        full_name = attrs.get("full_name") or attrs.get("name")
        phone_number = attrs.get("phone_number") or attrs.get("phone")
        license_number = attrs.get("license_number") or attrs.get("license_id")
        if not full_name:
            raise serializers.ValidationError(
                {
                    "detail": "Missing required field.",
                    "code": "missing_required_field",
                    "fields": {"full_name": "This field is required."},
                }
            )
        if not phone_number:
            raise serializers.ValidationError(
                {
                    "detail": "Missing required field.",
                    "code": "missing_required_field",
                    "fields": {"phone_number": "This field is required."},
                }
            )
        if User.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError(
                {
                    "detail": "Phone number is already registered.",
                    "code": "duplicate_phone",
                    "fields": {
                        "phone_number": "A user with this phone number already exists."
                    },
                }
            )
        if not license_number:
            raise serializers.ValidationError(
                {
                    "detail": "Missing required field.",
                    "code": "missing_required_field",
                    "fields": {"license_number": "This field is required."},
                }
            )
        if (
            attrs.get("confirm_password")
            and attrs["password"] != attrs["confirm_password"]
        ):
            raise serializers.ValidationError(
                {"confirm_password": "Password and confirmation do not match."}
            )
        if PharmacistProfile.objects.filter(
            license_number__iexact=license_number
        ).exists():
            raise serializers.ValidationError(
                {
                    "license_number": "A pharmacist with this license number already exists."
                }
            )
        pharmacy = None
        pharmacy_id = attrs.get("pharmacy_id")
        if pharmacy_id is not None:
            try:
                pharmacy = Pharmacy.objects.get(pk=pharmacy_id)
            except Pharmacy.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "detail": "Selected pharmacy was not found.",
                        "code": "pharmacy_not_found",
                    }
                )
            if not pharmacy.is_contracted_with_organization:
                raise serializers.ValidationError(
                    {
                        "detail": "Selected pharmacy is not contracted.",
                        "code": "pharmacy_not_contracted",
                    }
                )
        elif not attrs.get("pharmacy_name") or not attrs.get("pharmacy_address"):
            raise serializers.ValidationError(
                {
                    "detail": "pharmacy_id is required.",
                    "code": "missing_required_field",
                    "fields": {
                        "pharmacy_id": "This field is required.",
                    },
                }
            )
        validate_registration_otp(
            phone_number,
            attrs["otp"],
            PhoneOTP.PURPOSE_PHARMACIST_REGISTER,
        )
        attrs["full_name"] = full_name
        attrs["phone_number"] = phone_number
        attrs["license_number"] = license_number
        if pharmacy is not None:
            attrs["pharmacy"] = pharmacy
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("phone", None)
        validated_data.pop("name", None)
        validated_data.pop("license_id", None)
        validated_data.pop("confirm_password", None)
        validated_data.pop("otp", None)
        pharmacy = validated_data.pop("pharmacy", None)
        selected_existing_pharmacy = pharmacy is not None
        validated_data.pop("pharmacy_id", None)
        if pharmacy is None:
            pharmacy = Pharmacy.objects.create(
                name=validated_data["pharmacy_name"],
                address=validated_data["pharmacy_address"],
                phone_number=validated_data.get("pharmacy_phone_number", ""),
                latitude=validated_data.get("latitude"),
                longitude=validated_data.get("longitude"),
            )
        user = User.objects.create_user(
            email=validated_data.get("email") or None,
            password=validated_data["password"],
            phone_number=validated_data.get("phone_number", ""),
            role=RoleChoices.PHARMACIST,
            is_active=True,
            is_verified=False,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        profile = PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name=validated_data["full_name"],
            license_number=validated_data.get("license_number", ""),
        )
        if not selected_existing_pharmacy:
            pharmacy.owner_user = user
            pharmacy.save(update_fields=["owner_user", "updated_at"])
        return profile

    def to_response(self, profile):
        return {
            "detail": "Registration submitted successfully",
            "approval_status": profile.user.approval_status,
            "user": build_compat_user_payload(profile.user),
            "profile": build_compat_pharmacist_profile_payload(profile),
        }


class PharmacistMeUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, required=False)
    license_number = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    pharmacy_name = serializers.CharField(max_length=255, required=False)
    pharmacy_address = serializers.CharField(max_length=255, required=False)
    pharmacy_phone_number = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )

    def update(self, instance, validated_data):
        user = instance.user
        pharmacy = instance.pharmacy

        if "full_name" in validated_data:
            instance.full_name = validated_data["full_name"]
        if "license_number" in validated_data:
            instance.license_number = validated_data["license_number"]
        instance.save()

        if "phone_number" in validated_data:
            user.phone_number = validated_data["phone_number"]
            user.save(update_fields=["phone_number", "updated_at"])

        pharmacy_field_map = {
            "pharmacy_name": "name",
            "pharmacy_address": "address",
            "pharmacy_phone_number": "phone_number",
            "latitude": "latitude",
            "longitude": "longitude",
        }
        changed_fields = []
        for serializer_field, model_field in pharmacy_field_map.items():
            if serializer_field in validated_data:
                setattr(pharmacy, model_field, validated_data[serializer_field])
                changed_fields.append(model_field)
        if changed_fields:
            changed_fields.append("updated_at")
            pharmacy.save(update_fields=changed_fields)

        instance.refresh_from_db()
        return instance
