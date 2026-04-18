from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from common.choices import RoleChoices

from .models import PharmacistProfile, Pharmacy

User = get_user_model()


class PharmacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = (
            'id',
            'name',
            'owner_user',
            'address',
            'latitude',
            'longitude',
            'is_contracted_with_organization',
            'organization',
            'phone_number',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate(self, attrs):
        request = self.context['request']
        staff_organization = getattr(
            getattr(request.user, 'organization_staff_profile', None),
            'organization',
            None,
        )
        organization = attrs.get('organization')
        if request.user.is_superuser or staff_organization is None or organization is None:
            return attrs
        if organization != staff_organization:
            raise serializers.ValidationError(
                'You can only manage pharmacies within your organization.'
            )
        return attrs


class PharmacistProfileSerializer(serializers.ModelSerializer):
    pharmacy = PharmacySerializer(read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    phone_number = serializers.CharField(source='user.phone_number', read_only=True)

    class Meta:
        model = PharmacistProfile
        fields = (
            'id',
            'email',
            'phone_number',
            'pharmacy',
            'full_name',
            'license_number',
            'is_approved',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'is_approved', 'created_at', 'updated_at')


class PharmacistRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone_number = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    full_name = serializers.CharField(max_length=255)
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

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        pharmacy = Pharmacy.objects.create(
            name=validated_data['pharmacy_name'],
            address=validated_data['pharmacy_address'],
            phone_number=validated_data.get('pharmacy_phone_number', ''),
            latitude=validated_data.get('latitude'),
            longitude=validated_data.get('longitude'),
        )
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            phone_number=validated_data.get('phone_number', ''),
            role=RoleChoices.PHARMACIST,
            is_active=True,
        )
        profile = PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name=validated_data['full_name'],
            license_number=validated_data.get('license_number', ''),
        )
        pharmacy.owner_user = user
        pharmacy.save(update_fields=['owner_user', 'updated_at'])
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

        if 'full_name' in validated_data:
            instance.full_name = validated_data['full_name']
        if 'license_number' in validated_data:
            instance.license_number = validated_data['license_number']
        instance.save()

        if 'phone_number' in validated_data:
            user.phone_number = validated_data['phone_number']
            user.save(update_fields=['phone_number', 'updated_at'])

        pharmacy_field_map = {
            'pharmacy_name': 'name',
            'pharmacy_address': 'address',
            'pharmacy_phone_number': 'phone_number',
            'latitude': 'latitude',
            'longitude': 'longitude',
        }
        changed_fields = []
        for serializer_field, model_field in pharmacy_field_map.items():
            if serializer_field in validated_data:
                setattr(pharmacy, model_field, validated_data[serializer_field])
                changed_fields.append(model_field)
        if changed_fields:
            changed_fields.append('updated_at')
            pharmacy.save(update_fields=changed_fields)

        instance.refresh_from_db()
        return instance
