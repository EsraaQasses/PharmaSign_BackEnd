from django.db import models


class RoleChoices(models.TextChoices):
    ADMIN = 'admin', 'Admin'
    PHARMACIST = 'pharmacist', 'Pharmacist'
    PATIENT = 'patient', 'Patient'


class GenderChoices(models.TextChoices):
    MALE = 'M', 'Male'
    FEMALE = 'F', 'Female'
    OTHER = 'O', 'Other'


class HearingDisabilityLevelChoices(models.TextChoices):
    MILD = 'mild', 'Mild'
    MODERATE = 'moderate', 'Moderate'
    SEVERE = 'severe', 'Severe'
    PROFOUND = 'profound', 'Profound'


class PrescriptionStatusChoices(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    CONFIRMED = 'confirmed', 'Confirmed'
    DELIVERED = 'delivered', 'Delivered'
    ARCHIVED = 'archived', 'Archived'


class PatientSessionAccessTypeChoices(models.TextChoices):
    QR_SCAN = 'qr_scan', 'QR Scan'
    LOGIN = 'login', 'Patient Login'


class PrescriptionAccessTypeChoices(models.TextChoices):
    VIEW = 'view', 'View'
    ITEM_UPDATE = 'item_update', 'Item Update'
    CONFIRM = 'confirm', 'Confirm'
    TRANSCRIBE = 'transcribe', 'Transcribe'


class TranscriptionStatusChoices(models.TextChoices):
    NOT_REQUESTED = 'not_requested', 'Not Requested'
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'

