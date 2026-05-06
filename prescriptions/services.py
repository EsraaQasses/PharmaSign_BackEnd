from django.utils import timezone

from common.choices import PrescriptionAccessTypeChoices
from common.choices import SignStatusChoices
from common.choices import TranscriptionStatusChoices
from transcriptions.exceptions import sanitize_transcription_error
from transcriptions.services import get_gemini_modules

from .models import PrescriptionAccessLog
from .transcription import get_transcription_backend

SIGN_GLOSS_PROMPT_TEMPLATE = """You are an expert Arabic Sign Language interpreter for pharmacy and medical instructions.

Convert the input into a simplified Syrian/Levantine Arabic sign-language gloss.
Return only the final gloss text. Do not include Markdown, labels, quotes, bullets, or explanations.

Style rules:
- Use simple Syrian/Levantine Arabic when natural.
- Preserve medication meaning, dosage, timing, duration, route of use, warnings, and negation.
- Do not invent a disease, dosage, warning, or duration that is not in the input.
- Remove Arabic diacritics.
- Prefer direct phrases such as: ?????? ?????? ????? ???? ????? ?????? ?????? ??????? ??? ?????? ?????? ????? ???? ?????? ??????.
- It is okay to repeat concepts for clarity, such as: ????? ?????? ??? ???? ???? ????.
- For timing, normalize when useful:
  ??? ?????? / ??? ????? -> ??? ?????
  ??? ?????? / ??? ????? -> ??? ?????
- For duration, normalize when useful:
  ???? ???? ???? -> ??? 5 ???
  ???? ???? ???? -> ??? 7 ???
- For doctor-review warnings, prefer natural phrasing such as: ???? ???? ???????? ???? ????? ???? ???????? ???? ????? ????.
- For usage instructions, prefer adding: ??? ????? or ??? ????????? before the dose when helpful.

Examples:
Original:
??? ??? ?? 8 ????? ??? ????? ???? ???? ????
Gloss:
??? ???? ?? 8 ????? ??? ????? ??? 5 ???

Original:
??? ?????? ?????? ??? ?????? ?? ????? ????? ???? ???? ?????? ??? ????? ???? ??? ?? ??? ??? ???? ???????
Gloss:
????? ????? ??? ?????? ??? ??? ????? ????? ????? ???? 3 ???? ?????? ??? ????? ??? ??? ??? ???? ???? ???????

Input:
{approved_text}

Generated Gloss:"""


class SignGenerationError(Exception):
    def __init__(self, message, *, safe_message=None):
        super().__init__(message)
        self.safe_message = safe_message or sanitize_transcription_error(message)


def log_prescription_access(prescription, user, access_type):
    return PrescriptionAccessLog.objects.create(
        prescription=prescription,
        accessed_by=user,
        access_type=access_type,
    )


def transcribe_prescription_item(prescription_item, *, requested_by, force=False):
    if not prescription_item.instructions_audio:
        raise ValueError('Cannot transcribe an item without instructions audio.')

    if (
        prescription_item.transcription_status == TranscriptionStatusChoices.COMPLETED
        and not force
    ):
        return prescription_item

    prescription_item.transcription_status = TranscriptionStatusChoices.PROCESSING
    prescription_item.transcription_requested_at = timezone.now()
    prescription_item.transcription_error_message = ''
    prescription_item.save(
        update_fields=[
            'transcription_status',
            'transcription_requested_at',
            'transcription_error_message',
            'updated_at',
        ]
    )

    backend = get_transcription_backend()
    try:
        result = backend.transcribe(prescription_item=prescription_item)
    except Exception as exc:
        prescription_item.transcription_status = TranscriptionStatusChoices.FAILED
        prescription_item.transcription_provider = getattr(backend, 'provider_name', '')
        prescription_item.transcription_completed_at = timezone.now()
        prescription_item.transcription_error_message = str(exc)
        prescription_item.save(
            update_fields=[
                'transcription_status',
                'transcription_provider',
                'transcription_completed_at',
                'transcription_error_message',
                'updated_at',
            ]
        )
        raise

    prescription_item.instructions_transcript_raw = result.raw_text
    if not prescription_item.instructions_transcript_edited:
        prescription_item.instructions_transcript_edited = result.raw_text
    prescription_item.transcription_status = TranscriptionStatusChoices.COMPLETED
    prescription_item.transcription_provider = result.provider_name
    prescription_item.transcription_completed_at = timezone.now()
    prescription_item.transcription_error_message = ''
    prescription_item.save(
        update_fields=[
            'instructions_transcript_raw',
            'instructions_transcript_edited',
            'transcription_status',
            'transcription_provider',
            'transcription_completed_at',
            'transcription_error_message',
            'updated_at',
        ]
    )
    log_prescription_access(
        prescription_item.prescription,
        requested_by,
        PrescriptionAccessTypeChoices.TRANSCRIBE,
    )
    return prescription_item


def generate_sign_gloss(approved_text):
    from django.conf import settings

    if not settings.GEMINI_API_KEY:
        raise SignGenerationError("Gemini API key is not configured.")

    prompt = SIGN_GLOSS_PROMPT_TEMPLATE.format(approved_text=approved_text)
    try:
        genai, _types = get_gemini_modules()
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_SIGN_MODEL,
            contents=prompt,
        )
    except Exception as exc:
        raise SignGenerationError(
            str(exc),
            safe_message=sanitize_transcription_error(str(exc)),
        ) from exc

    gloss_text = getattr(response, "text", None)
    if not gloss_text or not str(gloss_text).strip():
        raise SignGenerationError("Gemini returned an empty sign gloss.")
    return {
        "provider": "gemini",
        "model": settings.GEMINI_SIGN_MODEL,
        "gloss_text": str(gloss_text).strip(),
    }


def mark_prescription_item_sign_processing(item):
    item.sign_status = SignStatusChoices.PROCESSING
    item.save(update_fields=["sign_status", "updated_at"])
    return item


def mark_prescription_item_sign_completed(item, gloss_text):
    item.supporting_text = gloss_text
    item.sign_status = SignStatusChoices.COMPLETED
    item.save(update_fields=["supporting_text", "sign_status", "updated_at"])
    return item


def mark_prescription_item_sign_failed(item):
    item.sign_status = SignStatusChoices.FAILED
    item.save(update_fields=["sign_status", "updated_at"])
    return item
