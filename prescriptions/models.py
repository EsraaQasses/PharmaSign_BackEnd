from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from common.choices import (
    PrescriptionAccessTypeChoices,
    PrescriptionStatusChoices,
    SignStatusChoices,
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

MONEY_QUANTUM = Decimal("0.01")


def medicine_image_upload_to(instance, filename):
    return build_prescription_media_upload_path(instance, filename, "images")


def instructions_audio_upload_to(instance, filename):
    return build_prescription_media_upload_path(instance, filename, "audio")


def sign_language_video_upload_to(instance, filename):
    return build_prescription_media_upload_path(instance, filename, "sign-language")


class Prescription(TimeStampedModel):
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    pharmacist = models.ForeignKey(
        PharmacistProfile,
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    pharmacy = models.ForeignKey(
        Pharmacy,
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    session = models.ForeignKey(
        "patients.PatientSession",
        on_delete=models.SET_NULL,
        related_name="prescriptions",
        null=True,
        blank=True,
    )
    doctor_name = models.CharField(max_length=255)
    doctor_specialty = models.CharField(max_length=255, blank=True)
    diagnosis = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=PrescriptionStatusChoices.choices,
        default=PrescriptionStatusChoices.DRAFT,
    )
    prescribed_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="SYP")
    reused_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="reused_children",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-prescribed_at", "-created_at")
        indexes = [
            models.Index(fields=["patient", "-prescribed_at"]),
            models.Index(fields=["pharmacist", "status"]),
            models.Index(fields=["pharmacy", "status"]),
            models.Index(fields=["session"]),
        ]

    def clean(self):
        if (
            self.pharmacist_id
            and self.pharmacy_id
            and self.pharmacist.pharmacy_id != self.pharmacy_id
        ):
            raise ValidationError(
                {
                    "pharmacy": "Prescription pharmacy must match the pharmacist pharmacy."
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def recalculate_total_price(self):
        total = self.items.aggregate(total=Sum("line_total"))["total"] or Decimal(
            "0.00"
        )
        self.total_price = total.quantize(MONEY_QUANTUM)
        self.save(update_fields=["total_price", "updated_at"])

    def __str__(self):
        return f"Prescription #{self.pk} - {self.patient.full_name}"


class PrescriptionItem(TimeStampedModel):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    medicine_name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=100, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    instructions_text = models.TextField(blank=True)
    medicine_image = models.ImageField(
        upload_to=medicine_image_upload_to, null=True, blank=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
    sign_status = models.CharField(
        max_length=20,
        choices=SignStatusChoices.choices,
        default=SignStatusChoices.PENDING,
    )
    is_confirmed = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["prescription", "is_confirmed"]),
            models.Index(fields=["prescription", "sign_status"]),
            models.Index(fields=["medicine_name"]),
        ]

    def clean(self):
        if self.unit_price is None:
            self.unit_price = Decimal("0.00")
        if self.quantity is None:
            self.quantity = Decimal("1.00")
        self.unit_price = Decimal(str(self.unit_price))
        self.quantity = Decimal(str(self.quantity))
        if self.unit_price < 0:
            raise ValidationError({"unit_price": "Unit price must not be negative."})
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})
        if self.medicine_image:
            validate_image_upload(self.medicine_image)
        if self.instructions_audio:
            validate_audio_upload(self.instructions_audio)
            if self.transcription_status == TranscriptionStatusChoices.NOT_REQUESTED:
                self.transcription_status = TranscriptionStatusChoices.PENDING
        elif self.transcription_status not in {
            TranscriptionStatusChoices.COMPLETED,
        }:
            self.transcription_status = TranscriptionStatusChoices.NOT_REQUESTED
        if self.sign_language_video:
            validate_video_upload(self.sign_language_video)

    def calculate_line_total(self):
        self.unit_price = Decimal(str(self.unit_price or Decimal("0.00")))
        self.quantity = Decimal(str(self.quantity or Decimal("1.00")))
        self.line_total = (self.unit_price * self.quantity).quantize(MONEY_QUANTUM)

    def save(self, *args, **kwargs):
        price = Decimal(str(self.price or Decimal("0.00")))
        unit_price = Decimal(str(self.unit_price or Decimal("0.00")))
        if unit_price == Decimal("0.00") and price != Decimal("0.00"):
            self.unit_price = price
        if Decimal(str(self.unit_price or Decimal("0.00"))) <= Decimal("99999999.99"):
            self.price = self.unit_price
        self.calculate_line_total()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if {"price", "unit_price", "quantity"} & update_fields:
                update_fields.update({"price", "unit_price", "line_total"})
            kwargs["update_fields"] = list(update_fields)
        self.full_clean()
        result = super().save(*args, **kwargs)
        if self.prescription_id:
            self.prescription.recalculate_total_price()
        return result

    def delete(self, *args, **kwargs):
        prescription = self.prescription
        result = super().delete(*args, **kwargs)
        prescription.recalculate_total_price()
        return result

    def __str__(self):
        return self.medicine_name


class SignQualityReport(TimeStampedModel):
    REPORT_TYPE_SIGN_UNCLEAR = "sign_unclear"

    STATUS_OPEN = "open"
    STATUS_REVIEWED = "reviewed"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"

    REPORT_TYPE_CHOICES = ((REPORT_TYPE_SIGN_UNCLEAR, "Sign unclear"),)
    STATUS_CHOICES = (
        (STATUS_OPEN, "Open"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_DISMISSED, "Dismissed"),
    )

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="sign_quality_reports",
    )
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="sign_quality_reports",
    )
    prescription_item = models.ForeignKey(
        PrescriptionItem,
        on_delete=models.CASCADE,
        related_name="sign_quality_reports",
    )
    medicine_name = models.CharField(max_length=255)
    approved_instruction_text = models.TextField(blank=True)
    report_type = models.CharField(
        max_length=50,
        choices=REPORT_TYPE_CHOICES,
        default=REPORT_TYPE_SIGN_UNCLEAR,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    admin_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["prescription", "status"]),
            models.Index(fields=["prescription_item", "report_type", "status"]),
            models.Index(fields=["report_type", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "prescription_item", "report_type"],
                condition=models.Q(status="open"),
                name="unique_open_sign_quality_report",
            )
        ]

    def __str__(self):
        return f"{self.medicine_name} - {self.report_type} - {self.status}"


class PrescriptionAccessLog(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="access_logs",
    )
    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="prescription_access_logs",
        null=True,
        blank=True,
    )
    access_type = models.CharField(
        max_length=20, choices=PrescriptionAccessTypeChoices.choices
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["prescription", "timestamp"]),
            models.Index(fields=["access_type"]),
        ]

    def __str__(self):
        return f"{self.prescription_id} - {self.access_type}"
