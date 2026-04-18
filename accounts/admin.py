from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'email',
        'role',
        'phone_number',
        'is_staff',
        'is_active',
        'is_verified',
        'created_at',
    )
    list_filter = ('role', 'is_staff', 'is_active', 'is_verified')
    search_fields = ('email', 'phone_number')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'last_login')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (
            'Status',
            {
                'fields': (
                    'role',
                    'phone_number',
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'is_verified',
                )
            },
        ),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'phone_number',
                    'role',
                    'password1',
                    'password2',
                    'is_staff',
                    'is_active',
                    'is_verified',
                ),
            },
        ),
    )

