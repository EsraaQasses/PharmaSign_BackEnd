from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


def build_prescription_media_upload_path(instance, filename, media_type):
    extension = Path(filename).suffix.lower()
    generated_name = f'{uuid4().hex}{extension}'
    prescription_segment = str(instance.prescription_id or 'pending')
    return f'prescriptions/{prescription_segment}/{media_type}/{generated_name}'


def validate_file_extension(uploaded_file, *, allowed_extensions, label):
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions))
        raise ValidationError(f'{label} must use one of these extensions: {allowed}.')


def validate_file_size(uploaded_file, *, max_bytes, label):
    if uploaded_file.size > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        raise ValidationError(f'{label} exceeds the {max_mb:.1f} MB size limit.')


def validate_content_type(uploaded_file, *, allowed_content_types, label):
    content_type = getattr(uploaded_file, 'content_type', '') or ''
    if content_type and content_type.lower() not in allowed_content_types:
        allowed = ', '.join(sorted(allowed_content_types))
        raise ValidationError(f'{label} must use one of these content types: {allowed}.')


def validate_image_upload(uploaded_file):
    validate_file_extension(
        uploaded_file,
        allowed_extensions=settings.PHARMASIGN_ALLOWED_IMAGE_EXTENSIONS,
        label='Medicine image',
    )
    validate_file_size(
        uploaded_file,
        max_bytes=settings.PHARMASIGN_MAX_IMAGE_UPLOAD_BYTES,
        label='Medicine image',
    )
    validate_content_type(
        uploaded_file,
        allowed_content_types=settings.PHARMASIGN_ALLOWED_IMAGE_CONTENT_TYPES,
        label='Medicine image',
    )
    position = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else None
    try:
        Image.open(uploaded_file).verify()
    except (UnidentifiedImageError, OSError):
        raise ValidationError('Medicine image is not a valid image file.')
    finally:
        if hasattr(uploaded_file, 'seek'):
            uploaded_file.seek(position or 0)


def validate_audio_upload(uploaded_file):
    validate_file_extension(
        uploaded_file,
        allowed_extensions=settings.PHARMASIGN_ALLOWED_AUDIO_EXTENSIONS,
        label='Instructions audio',
    )
    validate_file_size(
        uploaded_file,
        max_bytes=settings.PHARMASIGN_MAX_AUDIO_UPLOAD_BYTES,
        label='Instructions audio',
    )
    validate_content_type(
        uploaded_file,
        allowed_content_types=settings.PHARMASIGN_ALLOWED_AUDIO_CONTENT_TYPES,
        label='Instructions audio',
    )


def validate_video_upload(uploaded_file):
    validate_file_extension(
        uploaded_file,
        allowed_extensions=settings.PHARMASIGN_ALLOWED_VIDEO_EXTENSIONS,
        label='Sign language video',
    )
    validate_file_size(
        uploaded_file,
        max_bytes=settings.PHARMASIGN_MAX_VIDEO_UPLOAD_BYTES,
        label='Sign language video',
    )
    validate_content_type(
        uploaded_file,
        allowed_content_types=settings.PHARMASIGN_ALLOWED_VIDEO_CONTENT_TYPES,
        label='Sign language video',
    )
