from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone
from common.choices import ApprovalStatusChoices, RoleChoices
from common.models import TimeStampedModel


class UserManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra_fields):
        email = self.normalize_email(email) if email else None
        if extra_fields.get("phone_number") == "":
            extra_fields["phone_number"] = None
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", RoleChoices.ADMIN)
        extra_fields.setdefault("approval_status", ApprovalStatusChoices.APPROVED)
        extra_fields.setdefault("is_verified", True)
        if not email:
            raise ValueError("Superuser must have an email address.")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    email = models.EmailField(unique=True, db_index=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    role = models.CharField(
        max_length=20, choices=RoleChoices.choices, default=RoleChoices.PATIENT
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatusChoices.choices,
        default=ApprovalStatusChoices.APPROVED,
        db_index=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="approved_users",
        null=True,
        blank=True,
    )
    rejection_reason = models.TextField(blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["role", "approval_status"]),
        ]

    def __str__(self):
        return self.email or self.phone_number or f"User #{self.pk}"


class PhoneOTP(TimeStampedModel):
    PURPOSE_PATIENT_REGISTER = "patient_register"
    PURPOSE_PHARMACIST_REGISTER = "pharmacist_register"
    PURPOSE_CHOICES = (
        (PURPOSE_PATIENT_REGISTER, "Patient registration"),
        (PURPOSE_PHARMACIST_REGISTER, "Pharmacist registration"),
    )

    phone_number = models.CharField(max_length=20, db_index=True)
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="phone_otps",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["phone_number", "purpose"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["used_at"]),
        ]

    def set_code(self, code):
        self.code_hash = make_password(code)

    def check_code(self, code):
        return check_password(code, self.code_hash)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_locked(self):
        return self.used_at is not None or self.attempts >= self.max_attempts

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at", "updated_at"])

    def __str__(self):
        return f"{self.phone_number} - {self.purpose}"
