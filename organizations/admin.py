from django.contrib import admin
from .models import Organization, OrganizationStaffProfile


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'created_at')
    search_fields = ('name', 'phone')
    ordering = ('-created_at',)


@admin.register(OrganizationStaffProfile)
class OrganizationStaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'job_title', 'can_manage_patients')
    list_filter = ('can_manage_patients', 'can_manage_pharmacists')
    search_fields = ('user__email', 'organization__name')
