from django.conf import settings
from rest_framework import serializers


SUPPORTED_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/webm",
}


def validate_transcription_audio_upload(audio_file):
    content_type = (getattr(audio_file, "content_type", "") or "").lower()
    if content_type not in SUPPORTED_AUDIO_CONTENT_TYPES:
        raise serializers.ValidationError("Unsupported audio file type.")

    max_size_mb = settings.MAX_AUDIO_UPLOAD_SIZE_MB
    max_size_bytes = max_size_mb * 1024 * 1024
    if audio_file.size > max_size_bytes:
        raise serializers.ValidationError(
            f"Audio file size must not exceed {max_size_mb}MB."
        )

    return audio_file
