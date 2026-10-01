from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from common.choices import RoleChoices
from common.fields import EncryptedTextField
from common.models import TimeStampedModel
from patients.models import PatientProfile


class DoctorProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    full_name = models.CharField(max_length=255)
    specialty = models.CharField(max_length=255, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    workplace = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    is_approved = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("full_name",)
        indexes = [
            models.Index(fields=["is_approved"]),
            models.Index(fields=["specialty"]),
        ]

    def clean(self):
        if self.user_id and self.user.role != RoleChoices.DOCTOR:
            raise ValidationError({"user": "Doctor profile requires a doctor user."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class MedicalVisit(TimeStampedModel):
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="medical_visits",
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.PROTECT,
        related_name="medical_visits",
    )
    visited_at = models.DateTimeField(default=timezone.now, db_index=True)
    diagnosis = EncryptedTextField(blank=True)
    doctor_notes = EncryptedTextField(blank=True)
    follow_up_notes = EncryptedTextField(blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-visited_at", "-created_at")
        indexes = [
            models.Index(fields=["patient", "-visited_at"]),
            models.Index(fields=["doctor", "-visited_at"]),
        ]

    def __str__(self):
        return f"Visit #{self.pk} - {self.patient.full_name}"


class MedicalVisitMedication(TimeStampedModel):
    visit = models.ForeignKey(
        MedicalVisit,
        on_delete=models.CASCADE,
        related_name="medications",
    )
    medicine_name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=100, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    doctor_instructions = EncryptedTextField(blank=True)
    notes = EncryptedTextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=["visit", "medicine_name"])]

    def __str__(self):
        return self.medicine_name
