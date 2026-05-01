from django.contrib import admin

from .models import (
    PatientEnrollment,
    PatientLoginQR,
    PatientMedicalInfo,
    PatientProfile,
    PatientSession,
    PatientSessionQR,
    PatientSettings,
)


@admin.register(PatientEnrollment)
class PatientEnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "organization",
        "birth_date",
        "phone_number",
        "is_account_created",
        "created_at",
    )
    list_filter = (
        "organization",
        "gender",
        "hearing_disability_level",
        "is_account_created",
    )
    search_fields = (
        "first_name",
        "last_name",
        "father_name",
        "mother_name",
        "phone_number",
    )
    autocomplete_fields = ("organization", "patient_profile", "created_by")


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "user",
        "organization",
        "phone_number",
        "qr_is_active",
        "is_self_registered",
        "created_at",
    )
    list_filter = ("organization", "qr_is_active", "is_self_registered", "gender")
    search_fields = ("full_name", "user__email", "phone_number", "qr_code_value")
    autocomplete_fields = ("user", "organization")


@admin.register(PatientMedicalInfo)
class PatientMedicalInfoAdmin(admin.ModelAdmin):
    list_display = ("patient", "is_pregnant", "is_breastfeeding", "updated_at")
    search_fields = ("patient__full_name", "patient__user__email", "allergies")
    autocomplete_fields = ("patient",)


@admin.register(PatientSettings)
class PatientSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "notifications_enabled",
        "prescription_reminders",
        "dark_mode",
        "use_biometrics",
        "updated_at",
    )
    list_filter = (
        "notifications_enabled",
        "prescription_reminders",
        "dark_mode",
        "use_biometrics",
    )
    search_fields = ("patient__full_name", "patient__user__email")
    autocomplete_fields = ("patient",)


@admin.register(PatientLoginQR)
class PatientLoginQRAdmin(admin.ModelAdmin):
    list_display = ("patient", "is_active", "created_by", "created_at", "revoked_at")
    list_filter = ("is_active", "created_at", "revoked_at")
    search_fields = ("patient__full_name", "patient__user__phone_number")
    readonly_fields = ("token_hash", "created_at", "updated_at", "revoked_at")
    autocomplete_fields = ("patient", "created_by")


@admin.register(PatientSessionQR)
class PatientSessionQRAdmin(admin.ModelAdmin):
    list_display = ("patient", "expires_at", "used_at", "revoked_at", "created_at")
    list_filter = ("expires_at", "used_at", "revoked_at")
    search_fields = ("patient__full_name", "patient__user__phone_number")
    readonly_fields = (
        "token_hash",
        "expires_at",
        "used_at",
        "revoked_at",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("patient",)


@admin.register(PatientSession)
class PatientSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "pharmacist",
        "pharmacy",
        "status",
        "access_type",
        "started_at",
        "expires_at",
        "ended_at",
    )
    list_filter = ("status", "access_type", "pharmacy", "started_at")
    search_fields = (
        "patient__full_name",
        "pharmacist__full_name",
        "pharmacy__name",
        "qr_code_value_snapshot",
    )
    autocomplete_fields = ("patient", "pharmacist", "pharmacy")
