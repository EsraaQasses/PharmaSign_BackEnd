from pathlib import Path

from django.conf import settings
from rest_framework import serializers


SUPPORTED_AUDIO_EXTENSIONS = {
    ".3gp",
    ".3gpp",
    ".aac",
    ".amr",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".wave",
    ".webm",
}
SUPPORTED_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/vnd.wave",
    "audio/ogg",
    "audio/opus",
    "audio/webm",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/flac",
    "audio/x-flac",
    "audio/amr",
    "audio/3gpp",
    "video/3gpp",
    "application/ogg",
    "application/octet-stream",
    "audio/m4a",
}
UNSUPPORTED_AUDIO_MESSAGE = (
    "Unsupported audio file type. Allowed formats include mp3, wav, ogg, opus, "
    "webm, m4a, mp4, aac, flac, amr, 3gp."
)


def _audio_extension(audio_file):
    return Path(getattr(audio_file, "name", "") or "").suffix.lower()


def validate_transcription_audio_upload(audio_file):
    content_type = (getattr(audio_file, "content_type", "") or "").lower()
    extension = _audio_extension(audio_file)
    if not getattr(audio_file, "name", None) or audio_file.size == 0:
        raise serializers.ValidationError(
            {"detail": "Invalid audio file.", "code": "invalid_audio_file"}
        )
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise serializers.ValidationError(
            {"detail": UNSUPPORTED_AUDIO_MESSAGE, "code": "unsupported_audio_type"}
        )
    if content_type and content_type not in SUPPORTED_AUDIO_CONTENT_TYPES:
        raise serializers.ValidationError(
            {"detail": UNSUPPORTED_AUDIO_MESSAGE, "code": "unsupported_audio_type"}
        )

    max_size_mb = settings.MAX_AUDIO_UPLOAD_SIZE_MB
    max_size_bytes = max_size_mb * 1024 * 1024
    if audio_file.size > max_size_bytes:
        raise serializers.ValidationError(
            {
                "detail": f"Audio file size must not exceed {max_size_mb}MB.",
                "code": "audio_too_large",
            }
        )

    return audio_file
