from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.choices import RoleChoices
from common.models import TimeStampedModel


class Organization(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ('name',)
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


class OrganizationStaffProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organization_staff_profile',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='staff_members',
    )
    job_title = models.CharField(max_length=255, blank=True)
    can_manage_patients = models.BooleanField(default=True)
    can_manage_pharmacists = models.BooleanField(default=False)

    class Meta:
        ordering = ('organization__name', 'user__email')
        indexes = [
            models.Index(fields=['organization']),
            models.Index(fields=['can_manage_patients', 'can_manage_pharmacists']),
        ]

    def clean(self):
        if self.user_id and self.user.role != RoleChoices.ADMIN:
            raise ValidationError(
                {'user': 'Organization staff users must use the admin role.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user.email} - {self.organization.name}'
