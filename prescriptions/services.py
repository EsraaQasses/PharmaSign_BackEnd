from django.utils import timezone

from common.choices import PrescriptionAccessTypeChoices
from common.choices import TranscriptionStatusChoices

from .models import PrescriptionAccessLog
from .transcription import get_transcription_backend


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
