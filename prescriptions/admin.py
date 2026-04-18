from django.contrib import admin

from .models import Prescription, PrescriptionAccessLog, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'patient',
        'pharmacist',
        'pharmacy',
        'status',
        'prescribed_at',
        'delivered_at',
    )
    list_filter = ('status', 'pharmacy', 'prescribed_at')
    search_fields = ('patient__full_name', 'doctor_name', 'pharmacy__name')
    autocomplete_fields = ('patient', 'pharmacist', 'pharmacy', 'reused_from')
    inlines = [PrescriptionItemInline]


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = ('medicine_name', 'prescription', 'price', 'quantity', 'is_confirmed')
    list_filter = ('is_confirmed',)
    search_fields = ('medicine_name', 'prescription__patient__full_name')
    autocomplete_fields = ('prescription',)


@admin.register(PrescriptionAccessLog)
class PrescriptionAccessLogAdmin(admin.ModelAdmin):
    list_display = ('prescription', 'accessed_by', 'access_type', 'timestamp')
    list_filter = ('access_type', 'timestamp')
    search_fields = ('prescription__patient__full_name', 'accessed_by__email')
    autocomplete_fields = ('prescription', 'accessed_by')
