import secrets

from django.contrib.auth.hashers import check_password, make_password


def generate_qr_code_value(model_class=None, field_name='qr_code_value'):
    """
    Generate a unique QR token string.
    If a model class is provided, uniqueness is checked against that field.
    """
    while True:
        token = secrets.token_urlsafe(24)
        if model_class is None:
            return token
        if not model_class.objects.filter(**{field_name: token}).exists():
            return token


def hash_pin(pin: str) -> str:
    return make_password(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    if not pin_hash:
        return False
    return check_password(pin, pin_hash)
