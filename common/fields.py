import logging
import base64
import hashlib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def get_field_encryption_key():
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
    if key:
        return key.encode() if isinstance(key, str) else key
    if not settings.DEBUG:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY must be set in settings when DEBUG=False."
        )
    digest = hashlib.sha256(str(settings.SECRET_KEY).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def decrypt_encrypted_field_value(value, default=""):
    if value is None or value == "":
        return default
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return str(value)
    if not value.startswith("gAAAAA"):
        return value
    try:
        decrypted = Fernet(get_field_encryption_key()).decrypt(value.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        logger.warning("Encrypted field value could not be decrypted.")
        return default
    except Exception as exc:
        logger.warning("Encrypted field value could not be decrypted: %s", exc)
        return default


class EncryptedFieldMixin:
    description = "Field-level encrypted field using cryptography.fernet"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fernet = None

    @property
    def fernet(self):
        if self._fernet is None:
            try:
                self._fernet = Fernet(get_field_encryption_key())
            except Exception as exc:
                raise ImproperlyConfigured(
                    f"FIELD_ENCRYPTION_KEY is invalid: {exc}"
                ) from exc
        return self._fernet

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            value = str(value)
        if value.startswith("gAAAAA"):
            try:
                self.fernet.decrypt(value.encode("utf-8"))
                return value
            except InvalidToken:
                pass
        encrypted = self.fernet.encrypt(value.encode())
        return encrypted.decode("utf-8")

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return self._decrypt_value(value)

    def to_python(self, value):
        if value is None or value == "":
            return value
        if isinstance(value, str):
            if value.startswith("gAAAAA"):
                return self._decrypt_value(value)
            return value
        return super().to_python(value)

    def _decrypt_value(self, value):
        try:
            if isinstance(value, str):
                value = value.encode()
            decrypted = self.fernet.decrypt(value)
            return decrypted.decode('utf-8')
        except InvalidToken:
            # Existing databases may contain plaintext from before field encryption.
            logger.warning("Decryption failed. Returning plain database value.")
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value
        except Exception as exc:
            logger.error(f"Error decrypting field value: {exc}")
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value


class EncryptedTextField(EncryptedFieldMixin, models.TextField):
    pass


class EncryptedCharField(EncryptedFieldMixin, models.CharField):
    def __init__(self, *args, **kwargs):
        if "max_length" in kwargs:
            original_max_length = kwargs["max_length"]
            if original_max_length < 255:
                kwargs["max_length"] = 255
        super().__init__(*args, **kwargs)
