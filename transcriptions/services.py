import os
from django.conf import settings

from .exceptions import AudioTranscriptionError, sanitize_transcription_error


PROVIDER_GROQ = "groq"
GROQ_TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
PROVIDER_NAMES = {
    PROVIDER_GROQ: "groq_whisper",
}


class TranscriptionError(Exception):
    pass


def get_transcription_provider():
    return str(settings.TRANSCRIPTION_PROVIDER).strip().lower()


def get_transcription_provider_name():
    return PROVIDER_NAMES.get(
        get_transcription_provider(), get_transcription_provider()
    )


def transcribe_audio_file(audio_file) -> str:
    provider = get_transcription_provider()
    if provider == PROVIDER_GROQ:
        return transcribe_audio_file_with_groq(audio_file)
    raise AudioTranscriptionError(f"Unsupported transcription provider: {provider}.")


def transcribe_audio_file_with_groq(audio_file) -> str:
    if isinstance(audio_file, (str, os.PathLike)):
        return transcribe_audio_file_path_with_groq(str(audio_file))

    if not settings.GROQ_API_KEY:
        raise AudioTranscriptionError("Groq API key is not configured.")

    try:
        if hasattr(audio_file, "seek"):
            audio_file.seek(0)
        filename = getattr(audio_file, "name", "audio")
        file_payload = (
            filename,
            audio_file.read(),
        )
        client = get_groq_client_class()(api_key=settings.GROQ_API_KEY)
        result = client.audio.transcriptions.create(
            file=file_payload,
            model=settings.GROQ_WHISPER_MODEL,
            temperature=0,
            response_format="verbose_json",
        )
    except Exception as exc:
        raise AudioTranscriptionError(
            str(exc),
            safe_message=sanitize_transcription_error(str(exc)),
        ) from exc

    text = getattr(result, "text", None)
    if text is None and isinstance(result, dict):
        text = result.get("text")
    if not text:
        raise AudioTranscriptionError("Transcription provider returned empty text.")
    return text.strip()


def transcribe_audio_file_path_with_groq(file_path: str) -> str:
    if not settings.GROQ_API_KEY:
        raise TranscriptionError("Groq API key is not configured.")

    try:
        client = get_groq_client_class()(api_key=settings.GROQ_API_KEY)
        with open(file_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                file=audio_file,
                model=GROQ_TRANSCRIPTION_MODEL,
                response_format="verbose_json",
            )
    except Exception as exc:
        raise TranscriptionError(
            f"Audio transcription provider failed: {str(exc)}"
        ) from exc

    text = getattr(result, "text", None)
    if text is None and isinstance(result, dict):
        text = result.get("text")
    if not text or not str(text).strip():
        raise TranscriptionError("Transcription provider returned empty text.")
    return str(text).strip()


def get_groq_client_class():
    from groq import Groq

    return Groq
