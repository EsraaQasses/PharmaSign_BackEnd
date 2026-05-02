import logging
import random

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import PhoneOTP

logger = logging.getLogger(__name__)

OTP_EXPIRY_SECONDS = 300


def send_registration_otp_whatsapp(phone_number, otp):
    if settings.DEBUG:
        logger.warning("Development registration OTP for %s: %s", phone_number, otp)
        print(f"Development registration OTP for {phone_number}: {otp}")
        return
    logger.info("WhatsApp OTP provider is not configured; OTP was not sent.")
    return


def registration_purpose_for_role(role):
    if role == "patient":
        return PhoneOTP.PURPOSE_PATIENT_REGISTER
    if role == "pharmacist":
        return PhoneOTP.PURPOSE_PHARMACIST_REGISTER
    raise serializers.ValidationError({"role": "Role must be patient or pharmacist."})


def generate_registration_otp(phone_number, purpose):
    PhoneOTP.objects.filter(
        phone_number=phone_number,
        purpose=purpose,
        used_at__isnull=True,
    ).update(used_at=timezone.now())

    otp = f"{random.SystemRandom().randint(0, 999999):06d}"
    challenge = PhoneOTP(
        phone_number=phone_number,
        purpose=purpose,
        expires_at=timezone.now() + timezone.timedelta(seconds=OTP_EXPIRY_SECONDS),
    )
    challenge.set_code(otp)
    challenge.save()
    send_registration_otp_whatsapp(phone_number, otp)
    return otp, challenge


def validate_registration_otp(phone_number, otp, purpose):
    challenge = (
        PhoneOTP.objects.filter(
            phone_number=phone_number,
            purpose=purpose,
            used_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if not challenge:
        raise serializers.ValidationError({"detail": "Invalid OTP."})
    if challenge.attempts >= challenge.max_attempts:
        challenge.mark_used()
        raise serializers.ValidationError({"detail": "Too many OTP attempts."})
    if challenge.is_expired:
        challenge.mark_used()
        raise serializers.ValidationError({"detail": "OTP has expired."})
    if not challenge.check_code(otp):
        challenge.attempts += 1
        update_fields = ["attempts", "updated_at"]
        if challenge.attempts >= challenge.max_attempts:
            challenge.used_at = timezone.now()
            update_fields.append("used_at")
        challenge.save(update_fields=update_fields)
        if challenge.attempts >= challenge.max_attempts:
            raise serializers.ValidationError({"detail": "Too many OTP attempts."})
        raise serializers.ValidationError({"detail": "Invalid OTP."})
    challenge.mark_used()
    return challenge
