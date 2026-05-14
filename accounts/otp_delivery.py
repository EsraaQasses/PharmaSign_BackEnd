import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CHANNEL_DEBUG = "debug"
CHANNEL_TELEGRAM = "telegram"
SAFE_TELEGRAM_ERROR = "Telegram OTP delivery failed."


def _delivery_result(channel, sent, error=None):
    return {
        "channel": channel,
        "sent": sent,
        "error": error,
    }


def _telegram_config_is_complete():
    return bool(
        getattr(settings, "OTP_TELEGRAM_ENABLED", False)
        and getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        and getattr(settings, "TELEGRAM_DEFAULT_CHAT_ID", "")
    )


def _send_telegram_otp(phone_number, purpose, code):
    if not _telegram_config_is_complete():
        return _delivery_result(
            CHANNEL_TELEGRAM,
            False,
            "Telegram OTP delivery is not configured.",
        )

    token = settings.TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_DEFAULT_CHAT_ID,
        "text": (
            f"PharmaSign OTP code: {code}\n"
            f"Purpose: {purpose}\n"
            f"Phone: {phone_number}\n"
            "Expires in 5 minutes."
        ),
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        logger.warning("Telegram OTP delivery request failed.")
        return _delivery_result(CHANNEL_TELEGRAM, False, SAFE_TELEGRAM_ERROR)

    if response.status_code != 200:
        logger.warning(
            "Telegram OTP delivery failed with HTTP status %s.",
            response.status_code,
        )
        return _delivery_result(CHANNEL_TELEGRAM, False, SAFE_TELEGRAM_ERROR)

    try:
        response_body = response.json()
    except ValueError:
        logger.warning("Telegram OTP delivery returned invalid JSON.")
        return _delivery_result(CHANNEL_TELEGRAM, False, SAFE_TELEGRAM_ERROR)

    if response_body.get("ok") is not True:
        logger.warning("Telegram OTP delivery returned ok=false.")
        return _delivery_result(CHANNEL_TELEGRAM, False, SAFE_TELEGRAM_ERROR)

    return _delivery_result(CHANNEL_TELEGRAM, True)


def send_otp_code(phone_number: str, purpose: str, code: str) -> dict:
    channel = getattr(settings, "OTP_DELIVERY_CHANNEL", CHANNEL_DEBUG)
    if channel == CHANNEL_TELEGRAM:
        return _send_telegram_otp(phone_number, purpose, code)

    if settings.DEBUG:
        logger.warning("Development OTP generated for %s.", phone_number)
        return _delivery_result(CHANNEL_DEBUG, True)

    if getattr(settings, "OTP_DELIVERY_PROVIDER_CONFIGURED", False):
        logger.info("OTP delivery provider is configured, but no provider is implemented.")
        return _delivery_result(channel, True)

    return _delivery_result(
        channel,
        False,
        "OTP delivery provider is not configured",
    )
