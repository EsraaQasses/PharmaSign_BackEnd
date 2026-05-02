from dataclasses import dataclass

from django.conf import settings


@dataclass
class TranscriptionResult:
    raw_text: str
    provider_name: str


class BaseTranscriptionBackend:
    provider_name = 'base'

    def transcribe(self, *, prescription_item):
        raise NotImplementedError


class PlaceholderTranscriptionBackend(BaseTranscriptionBackend):
    provider_name = 'placeholder'

    def transcribe(self, *, prescription_item):
        filename = prescription_item.instructions_audio.name.rsplit('/', 1)[-1]
        raw_text = (
            f'Placeholder transcription for {prescription_item.medicine_name} '
            f'generated from {filename}.'
        )
        return TranscriptionResult(
            raw_text=raw_text,
            provider_name=self.provider_name,
        )


class FailingTranscriptionBackend(BaseTranscriptionBackend):
    provider_name = 'failing'

    def transcribe(self, *, prescription_item):
        raise RuntimeError('Transcription provider failed to process this audio file.')


BACKENDS = {
    'placeholder': PlaceholderTranscriptionBackend,
    'failing': FailingTranscriptionBackend,
}


def get_transcription_backend():
    backend_name = getattr(settings, 'PRESCRIPTION_TRANSCRIPTION_BACKEND', 'placeholder')
    backend_class = BACKENDS.get(backend_name)
    if backend_class is None:
        raise RuntimeError(f'Unsupported transcription provider: {backend_name}.')
    return backend_class()
