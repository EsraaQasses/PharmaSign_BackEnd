from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from common.choices import (
    GenderChoices,
    HearingDisabilityLevelChoices,
    PatientSessionAccessTypeChoices,
    RoleChoices,
)
from common.models import TimeStampedModel
from common.utils import hash_pin
from organizations.models import Organization


class PatientProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_profile",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="patients",
        null=True,
        blank=True,
    )
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=1,
        choices=GenderChoices.choices,
        blank=True,
    )
    address = models.CharField(max_length=255, blank=True)
    hearing_disability_level = models.CharField(
        max_length=20,
        choices=HearingDisabilityLevelChoices.choices,
        blank=True,
    )
    is_self_registered = models.BooleanField(default=False)
    qr_code_value = models.CharField(max_length=128, unique=True, null=True, blank=True)
    qr_is_active = models.BooleanField(default=False)
    record_access_pin_hash = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ("full_name",)
        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["full_name"]),
            models.Index(fields=["qr_is_active"]),
        ]

    @property
    def enrollment(self):
        return getattr(self, "enrollment_record", None)

    def set_record_access_pin(self, pin):
        self.record_access_pin_hash = hash_pin(pin)

    def clean(self):
        if self.user_id and self.user.role != RoleChoices.PATIENT:
            raise ValidationError({"user": "Patient profile requires a patient user."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class PatientEnrollment(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    patient_profile = models.OneToOneField(
        PatientProfile,
        on_delete=models.SET_NULL,
        related_name="enrollment_record",
        null=True,
        blank=True,
    )
    join_date = models.DateField(default=timezone.localdate)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    father_name = models.CharField(max_length=100, blank=True)
    mother_name = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField()
    gender = models.CharField(max_length=1, choices=GenderChoices.choices)
    address = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    hearing_disability_level = models.CharField(
        max_length=20,
        choices=HearingDisabilityLevelChoices.choices,
        blank=True,
    )
    notes = models.TextField(blank=True)
    is_account_created = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_patient_enrollments",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "last_name", "birth_date"]),
            models.Index(fields=["phone_number"]),
            models.Index(fields=["is_account_created"]),
        ]

    @property
    def full_name(self):
        return " ".join(
            part for part in [self.first_name, self.last_name] if part
        ).strip()

    def clean(self):
        duplicate_queryset = PatientEnrollment.objects.filter(
            organization=self.organization,
            first_name__iexact=self.first_name,
            last_name__iexact=self.last_name,
            birth_date=self.birth_date,
        )
        if self.father_name:
            duplicate_queryset = duplicate_queryset.filter(
                father_name__iexact=self.father_name
            )
        if self.pk:
            duplicate_queryset = duplicate_queryset.exclude(pk=self.pk)
        if duplicate_queryset.exists():
            raise ValidationError(
                {
                    "non_field_errors": (
                        "A very similar enrollment already exists for this organization."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if self.patient_profile_id:
            self.is_account_created = True
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.organization.name})"


class PatientMedicalInfo(TimeStampedModel):
    patient = models.OneToOneField(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="medical_info",
    )
    chronic_conditions = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    is_pregnant = models.BooleanField(null=True, blank=True)
    is_breastfeeding = models.BooleanField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Patient medical info"
        verbose_name_plural = "Patient medical info"

    def __str__(self):
        return f"Medical Info - {self.patient.full_name}"


class PatientSettings(TimeStampedModel):
    patient = models.OneToOneField(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    notifications_enabled = models.BooleanField(default=True)
    prescription_reminders = models.BooleanField(default=True)
    dark_mode = models.BooleanField(default=False)
    use_biometrics = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Patient settings"
        verbose_name_plural = "Patient settings"

    def __str__(self):
        return f"Settings - {self.patient.full_name}"


class PatientLoginQR(TimeStampedModel):
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="login_qr_tokens",
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_patient_login_qrs",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["patient", "is_active"]),
            models.Index(fields=["is_active", "revoked_at"]),
        ]
        verbose_name = "Patient login QR"
        verbose_name_plural = "Patient login QRs"

    def revoke(self):
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_active", "revoked_at", "updated_at"])

    def __str__(self):
        status = "active" if self.is_active else "revoked"
        return f"Login QR for {self.patient.full_name} ({status})"


class PatientSessionQR(TimeStampedModel):
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="session_qr_tokens",
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["patient", "used_at", "revoked_at"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["used_at"]),
            models.Index(fields=["revoked_at"]),
        ]
        verbose_name = "Patient session QR"
        verbose_name_plural = "Patient session QRs"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at", "updated_at"])

    def revoke(self):
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at", "updated_at"])

    def __str__(self):
        return f"Session QR for {self.patient.full_name}"


class PatientSession(TimeStampedModel):
    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
    )

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    pharmacist = models.ForeignKey(
        "pharmacies.PharmacistProfile",
        on_delete=models.CASCADE,
        related_name="patient_sessions",
    )
    pharmacy = models.ForeignKey(
        "pharmacies.Pharmacy",
        on_delete=models.CASCADE,
        related_name="patient_sessions",
    )
    access_type = models.CharField(
        max_length=20,
        choices=PatientSessionAccessTypeChoices.choices,
        default=PatientSessionAccessTypeChoices.QR_SCAN,
    )
    qr_code_value_snapshot = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at", "-created_at")
        indexes = [
            models.Index(fields=["patient", "-started_at"]),
            models.Index(fields=["pharmacist", "-started_at"]),
            models.Index(fields=["pharmacy", "-started_at"]),
            models.Index(fields=["access_type"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def clean(self):
        if self.pharmacist_id and self.pharmacy_id:
            if self.pharmacist.pharmacy_id != self.pharmacy_id:
                raise ValidationError(
                    {
                        "pharmacy": "Patient session pharmacy must match pharmacist pharmacy."
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Session #{self.pk} - {self.patient.full_name}"
