from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from common.choices import RoleChoices
from common.utils import verify_pin
from patients.models import PatientMedicalInfo, PatientProfile
from patients.services import assign_patient_qr_code

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'phone_number',
            'role',
            'is_active',
            'is_verified',
            'created_at',
            'updated_at',
            'profile',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'profile')

    def get_profile(self, obj):
        if hasattr(obj, 'patient_profile'):
            profile = obj.patient_profile
            return {
                'patient_id': profile.id,
                'full_name': profile.full_name,
                'qr_is_active': profile.qr_is_active,
            }
        if hasattr(obj, 'pharmacist_profile'):
            profile = obj.pharmacist_profile
            return {
                'pharmacist_id': profile.id,
                'full_name': profile.full_name,
                'pharmacy_id': profile.pharmacy_id,
                'is_approved': profile.is_approved,
            }
        if hasattr(obj, 'organization_staff_profile'):
            profile = obj.organization_staff_profile
            return {
                'organization_staff_profile_id': profile.id,
                'organization_id': profile.organization_id,
                'can_manage_patients': profile.can_manage_patients,
                'can_manage_pharmacists': profile.can_manage_pharmacists,
            }
        return None


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get('request'),
            email=attrs['email'],
            password=attrs['password'],
        )
        if not user:
            raise serializers.ValidationError({'detail': 'Invalid credentials.'})
        if not user.is_active:
            raise serializers.ValidationError({'detail': 'This account is inactive.'})
        attrs['user'] = user
        return attrs


class PatientQRLoginSerializer(serializers.Serializer):
    qr_code_value = serializers.CharField()
    pin = serializers.CharField(write_only=True, min_length=4, max_length=12)

    def validate(self, attrs):
        try:
            patient_profile = PatientProfile.objects.select_related('user').get(
                qr_code_value=attrs['qr_code_value'],
                qr_is_active=True,
            )
        except PatientProfile.DoesNotExist:
            raise serializers.ValidationError({'detail': 'Invalid QR code or PIN.'})

        user = patient_profile.user
        if user.role != RoleChoices.PATIENT or not user.is_active:
            raise serializers.ValidationError({'detail': 'Invalid QR code or PIN.'})

        if not verify_pin(attrs['pin'], patient_profile.record_access_pin_hash):
            raise serializers.ValidationError({'detail': 'Invalid QR code or PIN.'})

        attrs['user'] = user
        attrs['patient_profile'] = patient_profile
        return attrs


class PatientSelfRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone_number = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        min_length=8,
    )
    full_name = serializers.CharField(max_length=255)
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field('gender').choices,
        required=False,
        allow_blank=True,
    )
    address = serializers.CharField(required=False, allow_blank=True)
    hearing_disability_level = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field('hearing_disability_level').choices,
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
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            phone_number=validated_data.get('phone_number', ''),
            role=RoleChoices.PATIENT,
            is_active=True,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name=validated_data['full_name'],
            phone_number=validated_data.get('phone_number', ''),
            birth_date=validated_data.get('birth_date'),
            gender=validated_data.get('gender', ''),
            address=validated_data.get('address', ''),
            hearing_disability_level=validated_data.get('hearing_disability_level', ''),
            is_self_registered=True,
        )
        if validated_data.get('record_access_pin'):
            profile.set_record_access_pin(validated_data['record_access_pin'])
            profile.save(update_fields=['record_access_pin_hash', 'updated_at'])
        PatientMedicalInfo.objects.get_or_create(patient=profile)
        assign_patient_qr_code(profile)
        return user
