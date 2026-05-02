from django.db import models


class RoleChoices(models.TextChoices):
    ADMIN = "admin", "Admin"
    PHARMACIST = "pharmacist", "Pharmacist"
    PATIENT = "patient", "Patient"


class ApprovalStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class GenderChoices(models.TextChoices):
    MALE = "M", "Male"
    FEMALE = "F", "Female"
    OTHER = "O", "Other"


class HearingDisabilityLevelChoices(models.TextChoices):
    MILD = "mild", "Mild"
    MODERATE = "moderate", "Moderate"
    SEVERE = "severe", "Severe"
    PROFOUND = "profound", "Profound"


class PrescriptionStatusChoices(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    CANCELLED = "cancelled", "Cancelled"
    CONFIRMED = "confirmed", "Confirmed"
    DELIVERED = "delivered", "Delivered"
    ARCHIVED = "archived", "Archived"


class SignStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class PatientSessionAccessTypeChoices(models.TextChoices):
    QR_SCAN = "qr_scan", "QR Scan"
    LOGIN = "login", "Patient Login"


class PrescriptionAccessTypeChoices(models.TextChoices):
    VIEW = "view", "View"
    ITEM_UPDATE = "item_update", "Item Update"
    CONFIRM = "confirm", "Confirm"
    TRANSCRIBE = "transcribe", "Transcribe"


class TranscriptionStatusChoices(models.TextChoices):
    NOT_REQUESTED = "not_requested", "Not Requested"
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
