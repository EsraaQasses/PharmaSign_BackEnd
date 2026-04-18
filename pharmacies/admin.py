from django.contrib import admin

from .models import PharmacistProfile, Pharmacy


@admin.register(Pharmacy)
class PharmacyAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'organization',
        'is_contracted_with_organization',
        'phone_number',
        'created_at',
    )
    list_filter = ('is_contracted_with_organization', 'organization')
    search_fields = ('name', 'address', 'phone_number')
    autocomplete_fields = ('owner_user', 'organization')


@admin.register(PharmacistProfile)
class PharmacistProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'pharmacy', 'license_number', 'is_approved')
    list_filter = ('is_approved', 'pharmacy')
    search_fields = ('full_name', 'user__email', 'license_number', 'pharmacy__name')
    autocomplete_fields = ('user', 'pharmacy')
