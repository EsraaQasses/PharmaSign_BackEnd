from django.contrib import admin

from .models import DoctorProfile, MedicalVisit, MedicalVisitMedication


class MedicalVisitMedicationInline(admin.TabularInline):
    model = MedicalVisitMedication
    extra = 0


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialty", "workplace", "is_approved")
    list_filter = ("is_approved", "specialty")
    search_fields = ("full_name", "license_number", "user__email", "user__phone_number")


@admin.register(MedicalVisit)
class MedicalVisitAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "doctor", "visited_at", "follow_up_at")
    list_filter = ("visited_at", "doctor")
    search_fields = ("patient__full_name", "doctor__full_name")
    inlines = [MedicalVisitMedicationInline]
