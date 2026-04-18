from rest_framework import serializers

from .models import PatientEnrollment, PatientMedicalInfo, PatientProfile, PatientSession
from .services import assign_patient_qr_code, create_patient_account_from_enrollment


class PatientMedicalInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientMedicalInfo
        fields = (
            'chronic_conditions',
            'allergies',
            'is_pregnant',
            'is_breastfeeding',
            'notes',
            'updated_at',
        )
        read_only_fields = ('updated_at',)


class PatientProfileSerializer(serializers.ModelSerializer):
    medical_info = PatientMedicalInfoSerializer(read_only=True)
    enrollment_id = serializers.SerializerMethodField()

    class Meta:
        model = PatientProfile
        fields = (
            'id',
            'user',
            'organization',
            'enrollment_id',
            'full_name',
            'phone_number',
            'birth_date',
            'gender',
            'address',
            'hearing_disability_level',
            'is_self_registered',
            'qr_code_value',
            'qr_is_active',
            'created_at',
            'updated_at',
            'medical_info',
        )
        read_only_fields = (
            'id',
            'user',
            'qr_code_value',
            'qr_is_active',
            'created_at',
            'updated_at',
            'medical_info',
        )

    def get_enrollment_id(self, obj):
        enrollment = getattr(obj, 'enrollment_record', None)
        return getattr(enrollment, 'id', None)


class PatientEnrollmentSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    patient_profile_id = serializers.IntegerField(
        source='patient_profile.id',
        read_only=True,
    )
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = PatientEnrollment
        fields = (
            'id',
            'organization',
            'organization_name',
            'patient_profile_id',
            'join_date',
            'first_name',
            'last_name',
            'father_name',
            'mother_name',
            'birth_date',
            'gender',
            'address',
            'phone_number',
            'hearing_disability_level',
            'notes',
            'is_account_created',
            'created_by',
            'created_by_email',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'patient_profile_id',
            'is_account_created',
            'created_by',
            'created_by_email',
            'created_at',
            'updated_at',
        )

    def validate_organization(self, value):
        request = self.context['request']
        staff_organization = getattr(
            getattr(request.user, 'organization_staff_profile', None),
            'organization',
            None,
        )
        if request.user.is_superuser or staff_organization is None:
            return value
        if value != staff_organization:
            raise serializers.ValidationError(
                'You can only manage enrollments inside your organization.'
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
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def save(self, **kwargs):
        enrollment = self.context['enrollment']
        profile = create_patient_account_from_enrollment(
            enrollment,
            email=self.validated_data['email'],
            password=self.validated_data['password'],
            phone_number=self.validated_data.get('phone_number', ''),
            record_access_pin=self.validated_data.get('record_access_pin'),
        )
        return profile


class GeneratePatientQRSerializer(serializers.Serializer):
    regenerate = serializers.BooleanField(default=False)

    def save(self, **kwargs):
        patient = self.context['patient']
        qr_code_value = assign_patient_qr_code(
            patient,
            regenerate=self.validated_data.get('regenerate', False),
        )
        return {'qr_code_value': qr_code_value, 'qr_is_active': patient.qr_is_active}


class StartPatientSessionSerializer(serializers.Serializer):
    qr_code_value = serializers.CharField()


class PatientSessionSerializer(serializers.ModelSerializer):
    patient_id = serializers.IntegerField(source='patient.id', read_only=True)
    pharmacist_id = serializers.IntegerField(source='pharmacist.id', read_only=True)
    pharmacy_id = serializers.IntegerField(source='pharmacy.id', read_only=True)

    class Meta:
        model = PatientSession
        fields = (
            'id',
            'patient_id',
            'pharmacist_id',
            'pharmacy_id',
            'access_type',
            'qr_code_value_snapshot',
            'started_at',
            'ended_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields
