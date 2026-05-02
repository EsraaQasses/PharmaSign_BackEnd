import mimetypes

from django.conf import settings

from .exceptions import AudioTranscriptionError, sanitize_transcription_error


STRICT_PHARMACY_TRANSCRIPTION_PROMPT = (
    "Transcribe the Arabic pharmacy instruction audio exactly. "
    "Return only the spoken text. Do not summarize. Do not translate. "
    "Do not add explanations. Preserve medication names and numbers as spoken."
)


class TranscriptionError(AudioTranscriptionError):
    pass


def transcribe_audio_file(file_path: str, mime_type: str | None = None) -> dict:
    text = transcribe_audio_file_with_gemini(file_path, mime_type=mime_type)
    return {
        "provider": "gemini",
        "model": settings.GEMINI_MODEL,
        "transcript": text,
    }


def transcribe_audio_file_with_gemini(
    file_path: str, mime_type: str | None = None
) -> str:
    if not settings.GEMINI_API_KEY:
        raise TranscriptionError("Gemini API key is not configured.")

    resolved_mime_type = (
        mime_type or mimetypes.guess_type(file_path)[0] or "audio/mpeg"
    )

    try:
        genai, types = get_gemini_modules()
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        with open(file_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type=resolved_mime_type,
                        ),
                        types.Part.from_text(
                            text=STRICT_PHARMACY_TRANSCRIPTION_PROMPT
                        ),
                    ],
                )
            ],
        )
    except Exception as exc:
        raise TranscriptionError(
            str(exc),
            safe_message=sanitize_transcription_error(str(exc)),
        ) from exc

    text = getattr(response, "text", None)
    if not text or not str(text).strip():
        raise TranscriptionError("Gemini returned an empty transcript.")
    return str(text).strip()


def get_gemini_modules():
    from google import genai
    from google.genai import types

    return genai, types
