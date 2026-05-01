from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from common.choices import RoleChoices

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


class PharmacyCompatSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(max_length=255, required=False)
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
            "phone": instance.phone_number,
            "lat": instance.latitude,
            "lng": instance.longitude,
            "has_sign_service": True,
        }

    def update(self, instance, validated_data):
        field_map = {
            "name": "name",
            "address": "address",
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


class PharmacistRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
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
    pharmacy_name = serializers.CharField(max_length=255)
    pharmacy_address = serializers.CharField(max_length=255)
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

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        full_name = attrs.get("full_name") or attrs.get("name")
        phone_number = attrs.get("phone_number") or attrs.get("phone")
        license_number = attrs.get("license_number") or attrs.get("license_id")
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
        if not license_number:
            raise serializers.ValidationError(
                {"license_number": "This field is required."}
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
        attrs["full_name"] = full_name
        attrs["phone_number"] = phone_number
        attrs["license_number"] = license_number
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("phone", None)
        validated_data.pop("name", None)
        validated_data.pop("license_id", None)
        validated_data.pop("confirm_password", None)
        pharmacy = Pharmacy.objects.create(
            name=validated_data["pharmacy_name"],
            address=validated_data["pharmacy_address"],
            phone_number=validated_data.get("pharmacy_phone_number", ""),
            latitude=validated_data.get("latitude"),
            longitude=validated_data.get("longitude"),
        )
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            phone_number=validated_data.get("phone_number", ""),
            role=RoleChoices.PHARMACIST,
            is_active=True,
        )
        profile = PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name=validated_data["full_name"],
            license_number=validated_data.get("license_number", ""),
        )
        pharmacy.owner_user = user
        pharmacy.save(update_fields=["owner_user", "updated_at"])
        return profile


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
