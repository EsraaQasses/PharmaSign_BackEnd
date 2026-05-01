from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from hashlib import sha256
import secrets

from common.choices import RoleChoices
from common.utils import generate_qr_code_value

from .models import (
    PatientEnrollment,
    PatientLoginQR,
    PatientMedicalInfo,
    PatientProfile,
    PatientSessionQR,
)

User = get_user_model()


def assign_patient_qr_code(patient_profile, regenerate=False):
    if (
        patient_profile.qr_code_value
        and patient_profile.qr_is_active
        and not regenerate
    ):
        return patient_profile.qr_code_value

    patient_profile.qr_code_value = generate_qr_code_value(PatientProfile)
    patient_profile.qr_is_active = True
    patient_profile.save(update_fields=["qr_code_value", "qr_is_active", "updated_at"])
    return patient_profile.qr_code_value


def hash_patient_login_qr_token(token):
    return sha256(token.encode("utf-8")).hexdigest()


def generate_patient_login_qr(patient_profile, *, created_by=None):
    PatientLoginQR.objects.filter(patient=patient_profile, is_active=True).update(
        is_active=False,
        revoked_at=timezone.now(),
    )
    while True:
        token = secrets.token_urlsafe(32)
        token_hash = hash_patient_login_qr_token(token)
        if not PatientLoginQR.objects.filter(token_hash=token_hash).exists():
            break
    login_qr = PatientLoginQR.objects.create(
        patient=patient_profile,
        token_hash=token_hash,
        created_by=created_by,
    )
    return token, login_qr


def revoke_patient_login_qr(patient_profile):
    updated = PatientLoginQR.objects.filter(
        patient=patient_profile, is_active=True
    ).update(
        is_active=False,
        revoked_at=timezone.now(),
    )
    return updated


def get_patient_by_login_qr_token(token):
    token_hash = hash_patient_login_qr_token(token)
    return (
        PatientLoginQR.objects.select_related("patient", "patient__user")
        .filter(token_hash=token_hash)
        .first()
    )


def hash_patient_session_qr_token(token):
    return sha256(token.encode("utf-8")).hexdigest()


def generate_patient_session_qr(patient_profile, *, expires_in_seconds=300):
    PatientSessionQR.objects.filter(
        patient=patient_profile,
        used_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
    while True:
        token = secrets.token_urlsafe(32)
        token_hash = hash_patient_session_qr_token(token)
        if not PatientSessionQR.objects.filter(token_hash=token_hash).exists():
            break
    session_qr = PatientSessionQR.objects.create(
        patient=patient_profile,
        token_hash=token_hash,
        expires_at=timezone.now() + timezone.timedelta(seconds=expires_in_seconds),
    )
    return token, session_qr, expires_in_seconds


def get_patient_session_qr_by_token(token):
    token_hash = hash_patient_session_qr_token(token)
    return (
        PatientSessionQR.objects.select_related("patient", "patient__user")
        .filter(token_hash=token_hash)
        .first()
    )


@transaction.atomic
def create_patient_account_from_enrollment(
    enrollment,
    *,
    email,
    password,
    phone_number="",
    record_access_pin=None,
):
    if enrollment.patient_profile_id:
        raise ValidationError("An account already exists for this enrollment.")

    user = User.objects.create_user(
        email=email,
        password=password,
        phone_number=phone_number or enrollment.phone_number,
        role=RoleChoices.PATIENT,
        is_verified=True,
    )
    profile = PatientProfile.objects.create(
        user=user,
        organization=enrollment.organization,
        full_name=enrollment.full_name,
        phone_number=phone_number or enrollment.phone_number,
        birth_date=enrollment.birth_date,
        gender=enrollment.gender,
        address=enrollment.address,
        hearing_disability_level=enrollment.hearing_disability_level,
        is_self_registered=False,
    )
    if record_access_pin:
        profile.set_record_access_pin(record_access_pin)
        profile.save(update_fields=["record_access_pin_hash", "updated_at"])

    PatientMedicalInfo.objects.get_or_create(patient=profile)
    enrollment.patient_profile = profile
    enrollment.is_account_created = True
    enrollment.save(
        update_fields=["patient_profile", "is_account_created", "updated_at"]
    )
    assign_patient_qr_code(profile)
    return profile


def build_patient_summary(patient_profile):
    medical_info = getattr(patient_profile, "medical_info", None)
    latest_prescriptions = list(
        patient_profile.prescriptions.select_related("pharmacy")
        .prefetch_related("items")
        .order_by("-prescribed_at")[:3]
    )

    return {
        "patient": {
            "id": patient_profile.id,
            "full_name": patient_profile.full_name,
            "phone_number": patient_profile.phone_number,
            "birth_date": patient_profile.birth_date,
            "gender": patient_profile.gender,
            "hearing_disability_level": patient_profile.hearing_disability_level,
            "qr_is_active": patient_profile.qr_is_active,
        },
        "medical_info": {
            "chronic_conditions": getattr(medical_info, "chronic_conditions", ""),
            "allergies": getattr(medical_info, "allergies", ""),
            "is_pregnant": getattr(medical_info, "is_pregnant", None),
            "is_breastfeeding": getattr(medical_info, "is_breastfeeding", None),
            "notes": getattr(medical_info, "notes", ""),
            "regular_medications": getattr(medical_info, "notes", ""),
        },
        "latest_prescriptions": [
            {
                "id": prescription.id,
                "status": prescription.status,
                "doctor_name": prescription.doctor_name,
                "doctor_specialty": prescription.doctor_specialty,
                "pharmacy_name": prescription.pharmacy.name,
                "prescribed_at": prescription.prescribed_at,
                "items": [
                    {
                        "id": item.id,
                        "medicine_name": item.medicine_name,
                        "is_confirmed": item.is_confirmed,
                    }
                    for item in prescription.items.all()
                ],
            }
            for prescription in latest_prescriptions
        ],
    }
