from django.contrib import admin

from .models import PatientEnrollment, PatientMedicalInfo, PatientProfile, PatientSession


@admin.register(PatientEnrollment)
class PatientEnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'organization',
        'birth_date',
        'phone_number',
        'is_account_created',
        'created_at',
    )
    list_filter = ('organization', 'gender', 'hearing_disability_level', 'is_account_created')
    search_fields = (
        'first_name',
        'last_name',
        'father_name',
        'mother_name',
        'phone_number',
    )
    autocomplete_fields = ('organization', 'patient_profile', 'created_by')


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'user',
        'organization',
        'phone_number',
        'qr_is_active',
        'is_self_registered',
        'created_at',
    )
    list_filter = ('organization', 'qr_is_active', 'is_self_registered', 'gender')
    search_fields = ('full_name', 'user__email', 'phone_number', 'qr_code_value')
    autocomplete_fields = ('user', 'organization')


@admin.register(PatientMedicalInfo)
class PatientMedicalInfoAdmin(admin.ModelAdmin):
    list_display = ('patient', 'is_pregnant', 'is_breastfeeding', 'updated_at')
    search_fields = ('patient__full_name', 'patient__user__email', 'allergies')
    autocomplete_fields = ('patient',)


@admin.register(PatientSession)
class PatientSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'patient',
        'pharmacist',
        'pharmacy',
        'access_type',
        'started_at',
        'ended_at',
    )
    list_filter = ('access_type', 'pharmacy', 'started_at')
    search_fields = (
        'patient__full_name',
        'pharmacist__full_name',
        'pharmacy__name',
        'qr_code_value_snapshot',
    )
    autocomplete_fields = ('patient', 'pharmacist', 'pharmacy')
