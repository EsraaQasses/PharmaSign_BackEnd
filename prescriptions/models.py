from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from common.choices import (
    PrescriptionAccessTypeChoices,
    PrescriptionStatusChoices,
    TranscriptionStatusChoices,
)
from common.models import TimeStampedModel
from common.uploads import (
    build_prescription_media_upload_path,
    validate_audio_upload,
    validate_image_upload,
    validate_video_upload,
)
from patients.models import PatientProfile
from pharmacies.models import PharmacistProfile, Pharmacy


def medicine_image_upload_to(instance, filename):
    return build_prescription_media_upload_path(instance, filename, 'images')


def instructions_audio_upload_to(instance, filename):
    return build_prescription_media_upload_path(instance, filename, 'audio')


def sign_language_video_upload_to(instance, filename):
    return build_prescription_media_upload_path(instance, filename, 'sign-language')


class Prescription(TimeStampedModel):
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name='prescriptions',
    )
    pharmacist = models.ForeignKey(
        PharmacistProfile,
        on_delete=models.CASCADE,
        related_name='prescriptions',
    )
    pharmacy = models.ForeignKey(
        Pharmacy,
        on_delete=models.CASCADE,
        related_name='prescriptions',
    )
    doctor_name = models.CharField(max_length=255)
    doctor_specialty = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=PrescriptionStatusChoices.choices,
        default=PrescriptionStatusChoices.DRAFT,
    )
    prescribed_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    reused_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='reused_children',
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ('-prescribed_at', '-created_at')
        indexes = [
            models.Index(fields=['patient', '-prescribed_at']),
            models.Index(fields=['pharmacist', 'status']),
            models.Index(fields=['pharmacy', 'status']),
        ]

    def clean(self):
        if self.pharmacist_id and self.pharmacy_id and self.pharmacist.pharmacy_id != self.pharmacy_id:
            raise ValidationError(
                {'pharmacy': 'Prescription pharmacy must match the pharmacist pharmacy.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'Prescription #{self.pk} - {self.patient.full_name}'


class PrescriptionItem(TimeStampedModel):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name='items',
    )
    medicine_name = models.CharField(max_length=255)
    medicine_image = models.ImageField(upload_to=medicine_image_upload_to, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    instructions_audio = models.FileField(
        upload_to=instructions_audio_upload_to,
        null=True,
        blank=True,
    )
    transcription_status = models.CharField(
        max_length=20,
        choices=TranscriptionStatusChoices.choices,
        default=TranscriptionStatusChoices.NOT_REQUESTED,
    )
    transcription_provider = models.CharField(max_length=100, blank=True)
    transcription_requested_at = models.DateTimeField(null=True, blank=True)
    transcription_completed_at = models.DateTimeField(null=True, blank=True)
    transcription_error_message = models.TextField(blank=True)
    instructions_transcript_raw = models.TextField(blank=True)
    instructions_transcript_edited = models.TextField(blank=True)
    sign_language_video = models.FileField(
        upload_to=sign_language_video_upload_to,
        null=True,
        blank=True,
    )
    supporting_text = models.TextField(blank=True)
    is_confirmed = models.BooleanField(default=False)

    class Meta:
        ordering = ('created_at',)
        indexes = [
            models.Index(fields=['prescription', 'is_confirmed']),
            models.Index(fields=['medicine_name']),
        ]

    def clean(self):
        if self.medicine_image:
            validate_image_upload(self.medicine_image)
        if self.instructions_audio:
            validate_audio_upload(self.instructions_audio)
            if self.transcription_status == TranscriptionStatusChoices.NOT_REQUESTED:
                self.transcription_status = TranscriptionStatusChoices.PENDING
        elif self.transcription_status != TranscriptionStatusChoices.COMPLETED:
            self.transcription_status = TranscriptionStatusChoices.NOT_REQUESTED
        if self.sign_language_video:
            validate_video_upload(self.sign_language_video)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.medicine_name


class PrescriptionAccessLog(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name='access_logs',
    )
    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='prescription_access_logs',
        null=True,
        blank=True,
    )
    access_type = models.CharField(max_length=20, choices=PrescriptionAccessTypeChoices.choices)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-timestamp',)
        indexes = [
            models.Index(fields=['prescription', 'timestamp']),
            models.Index(fields=['access_type']),
        ]

    def __str__(self):
        return f'{self.prescription_id} - {self.access_type}'
