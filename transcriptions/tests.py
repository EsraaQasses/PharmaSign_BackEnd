from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import ApprovalStatusChoices, RoleChoices
from pharmacies.models import PharmacistProfile, Pharmacy
from .exceptions import AudioTranscriptionError, sanitize_transcription_error
from .services import TranscriptionError, get_transcription_provider_name, transcribe_audio_file


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


class TestGroqTranscriptionEndpointTests(APITestCase):
    endpoint = "/api/transcriptions/test-groq/"

    def create_user(self, *, role, approval_status, phone_number):
        return User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number=phone_number,
            role=role,
            approval_status=approval_status,
            is_verified=approval_status == ApprovalStatusChoices.APPROVED,
            is_active=True,
        )

    def create_pharmacist(self, *, approval_status, phone_number):
        user = self.create_user(
            role=RoleChoices.PHARMACIST,
            approval_status=approval_status,
            phone_number=phone_number,
        )
        pharmacy = Pharmacy.objects.create(
            name=f"Pharmacy {phone_number}",
            address="Damascus",
        )
        PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Test Pharmacist",
            is_approved=approval_status == ApprovalStatusChoices.APPROVED,
        )
        return user

    def audio_file(self, *, content_type="audio/mpeg", content=b"fake-audio"):
        return SimpleUploadedFile(
            "sample.mp3",
            content,
            content_type=content_type,
        )

    @patch("transcriptions.views.transcribe_audio_file_with_groq")
    def test_approved_pharmacist_can_call_test_endpoint(self, mock_transcribe):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559000",
        )
        mock_transcribe.return_value = "Take one tablet after food."
        self.client.force_authenticate(user)

        response = self.client.post(
            self.endpoint,
            {"audio": self.audio_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["provider"], "groq")
        self.assertEqual(response.data["model"], "whisper-large-v3-turbo")
        self.assertEqual(response.data["transcript"], "Take one tablet after food.")
        mock_transcribe.assert_called_once()

    @patch("transcriptions.views.transcribe_audio_file_with_groq")
    def test_pending_pharmacist_receives_403(self, mock_transcribe):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.PENDING,
            phone_number="5559001",
        )
        self.client.force_authenticate(user)

        response = self.client.post(
            self.endpoint,
            {"audio": self.audio_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_transcribe.assert_not_called()

    @patch("transcriptions.views.transcribe_audio_file_with_groq")
    def test_rejected_pharmacist_receives_403(self, mock_transcribe):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.REJECTED,
            phone_number="5559002",
        )
        self.client.force_authenticate(user)

        response = self.client.post(
            self.endpoint,
            {"audio": self.audio_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_transcribe.assert_not_called()

    @patch("transcriptions.views.transcribe_audio_file_with_groq")
    def test_approved_patient_receives_403(self, mock_transcribe):
        user = self.create_user(
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559003",
        )
        self.client.force_authenticate(user)

        response = self.client.post(
            self.endpoint,
            {"audio": self.audio_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_transcribe.assert_not_called()

    def test_missing_audio_returns_400(self):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559004",
        )
        self.client.force_authenticate(user)

        response = self.client.post(self.endpoint, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("audio", response.data)

    @patch("transcriptions.views.transcribe_audio_file_with_groq")
    def test_invalid_audio_type_returns_400(self, mock_transcribe):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559005",
        )
        self.client.force_authenticate(user)

        response = self.client.post(
            self.endpoint,
            {"audio": self.audio_file(content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("audio", response.data)
        mock_transcribe.assert_not_called()

    @patch("transcriptions.views.transcribe_audio_file_with_groq")
    def test_too_large_audio_returns_400(self, mock_transcribe):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559006",
        )
        self.client.force_authenticate(user)
        too_large_audio = self.audio_file(content=b"x" * (25 * 1024 * 1024 + 1))

        response = self.client.post(
            self.endpoint,
            {"audio": too_large_audio},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("audio", response.data)
        mock_transcribe.assert_not_called()

    @patch("transcriptions.views.transcribe_audio_file_with_groq")
    def test_groq_service_failure_returns_502(self, mock_transcribe):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559007",
        )
        mock_transcribe.side_effect = TranscriptionError("provider unavailable")
        self.client.force_authenticate(user)

        response = self.client.post(
            self.endpoint,
            {"audio": self.audio_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["status"], "failed")
        self.assertEqual(response.data["provider"], "groq")
        self.assertEqual(response.data["error"], "provider unavailable")
