from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.choices import RoleChoices
from common.models import TimeStampedModel
from organizations.models import Organization


class Pharmacy(TimeStampedModel):
    name = models.CharField(max_length=255)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='owned_pharmacies',
        null=True,
        blank=True,
    )
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_contracted_with_organization = models.BooleanField(default=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name='pharmacies',
        null=True,
        blank=True,
    )
    phone_number = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ('name',)
        indexes = [
            models.Index(fields=['organization', 'is_contracted_with_organization']),
            models.Index(fields=['name']),
        ]

    def clean(self):
        if self.is_contracted_with_organization and not self.organization_id:
            raise ValidationError(
                {'organization': 'Contracted pharmacies must be linked to an organization.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PharmacistProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pharmacist_profile',
    )
    pharmacy = models.ForeignKey(
        Pharmacy,
        on_delete=models.CASCADE,
        related_name='pharmacists',
    )
    full_name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=100, blank=True)
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ('full_name',)
        indexes = [
            models.Index(fields=['pharmacy']),
            models.Index(fields=['is_approved']),
        ]

    def clean(self):
        if self.user_id and self.user.role != RoleChoices.PHARMACIST:
            raise ValidationError({'user': 'Pharmacist profile requires a pharmacist user.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name
