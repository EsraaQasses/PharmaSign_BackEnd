from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .exceptions import AudioTranscriptionError, sanitize_transcription_error
from .services import get_transcription_provider_name, transcribe_audio_file


class TranscriptionServiceTests(TestCase):
    @override_settings(
        TRANSCRIPTION_PROVIDER="groq",
        GROQ_API_KEY="test-key",
        GROQ_WHISPER_MODEL="whisper-large-v3",
    )
    @patch("transcriptions.services.get_groq_client_class")
    def test_transcribe_audio_file_routes_to_groq(self, mock_get_groq_client_class):
        audio = SimpleUploadedFile(
            "instructions.mp3",
            b"fake-audio",
            content_type="audio/mpeg",
        )
        mock_groq = mock_get_groq_client_class.return_value
        client = mock_groq.return_value
        client.audio.transcriptions.create.return_value = SimpleNamespace(
            text=" Take one tablet after food. "
        )

        result = transcribe_audio_file(audio)

        self.assertEqual(result, "Take one tablet after food.")
        self.assertEqual(get_transcription_provider_name(), "groq_whisper")
        client.audio.transcriptions.create.assert_called_once()
        call_kwargs = client.audio.transcriptions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "whisper-large-v3")
        self.assertEqual(call_kwargs["temperature"], 0)
        self.assertEqual(call_kwargs["response_format"], "verbose_json")
        self.assertEqual(call_kwargs["file"][0], "instructions.mp3")
        self.assertEqual(call_kwargs["file"][1], b"fake-audio")
        self.assertEqual(len(call_kwargs["file"]), 2)

    @override_settings(TRANSCRIPTION_PROVIDER="groq", GROQ_API_KEY="")
    def test_transcribe_audio_file_requires_groq_api_key(self):
        audio = SimpleUploadedFile(
            "instructions.mp3",
            b"fake-audio",
            content_type="audio/mpeg",
        )

        with self.assertRaises(AudioTranscriptionError):
            transcribe_audio_file(audio)

    @override_settings(TRANSCRIPTION_PROVIDER="unsupported")
    def test_transcribe_audio_file_rejects_unsupported_provider(self):
        audio = SimpleUploadedFile(
            "instructions.mp3",
            b"fake-audio",
            content_type="audio/mpeg",
        )

        with self.assertRaises(AudioTranscriptionError):
            transcribe_audio_file(audio)

    def test_sanitize_transcription_error_hides_sensitive_values(self):
        self.assertEqual(
            sanitize_transcription_error("invalid api key gsk_secret"),
            "Audio transcription provider authentication failed.",
        )
