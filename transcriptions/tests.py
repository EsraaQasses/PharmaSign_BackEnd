import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import ApprovalStatusChoices, RoleChoices
from pharmacies.models import PharmacistProfile, Pharmacy

from .exceptions import sanitize_transcription_error
from .services import (
    TranscriptionError,
    transcribe_audio_file,
    transcribe_audio_file_with_gemini,
)


class TranscriptionServiceTests(TestCase):
    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-2.5-flash")
    @patch("transcriptions.services.get_gemini_modules")
    def test_transcribe_audio_file_routes_to_gemini(self, mock_get_gemini_modules):
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as temp_file:
            temp_file.write(b"fake-audio")
            temp_path = temp_file.name

        try:
            mock_genai = SimpleNamespace()
            mock_client = SimpleNamespace(models=SimpleNamespace())
            mock_client.models.generate_content = Mock(
                return_value=SimpleNamespace(text=" Take one tablet after food. ")
            )
            mock_genai.Client = lambda api_key: mock_client
            mock_types = SimpleNamespace(
                Content=lambda role, parts: SimpleNamespace(role=role, parts=parts),
                Part=SimpleNamespace(
                    from_bytes=lambda data, mime_type: {
                        "kind": "bytes",
                        "data": data,
                        "mime_type": mime_type,
                    },
                    from_text=lambda text: {"kind": "text", "text": text},
                ),
            )
            mock_get_gemini_modules.return_value = (mock_genai, mock_types)

            result = transcribe_audio_file(temp_path, mime_type="audio/mp4")

            self.assertEqual(
                result,
                {
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "transcript": "Take one tablet after food.",
                },
            )
            mock_client.models.generate_content.assert_called_once()
            call_kwargs = mock_client.models.generate_content.call_args.kwargs
            self.assertEqual(call_kwargs["model"], "gemini-2.5-flash")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @override_settings(GEMINI_API_KEY="")
    def test_transcribe_audio_file_with_gemini_requires_api_key(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(b"audio")
            temp_path = temp_file.name

        try:
            with self.assertRaises(TranscriptionError) as exc:
                transcribe_audio_file_with_gemini(temp_path, mime_type="audio/wav")
            self.assertEqual(str(exc.exception), "Gemini API key is not configured.")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-2.5-flash")
    @patch("transcriptions.services.get_gemini_modules")
    def test_gemini_empty_transcript_is_rejected(self, mock_get_gemini_modules):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(b"audio")
            temp_path = temp_file.name

        try:
            mock_genai = SimpleNamespace()
            mock_client = SimpleNamespace(models=SimpleNamespace())
            mock_client.models.generate_content = Mock(
                return_value=SimpleNamespace(text="")
            )
            mock_genai.Client = lambda api_key: mock_client
            mock_types = SimpleNamespace(
                Content=lambda role, parts: SimpleNamespace(role=role, parts=parts),
                Part=SimpleNamespace(
                    from_bytes=lambda data, mime_type: {
                        "kind": "bytes",
                        "data": data,
                        "mime_type": mime_type,
                    },
                    from_text=lambda text: {"kind": "text", "text": text},
                ),
            )
            mock_get_gemini_modules.return_value = (mock_genai, mock_types)

            with self.assertRaises(TranscriptionError) as exc:
                transcribe_audio_file_with_gemini(temp_path, mime_type="audio/wav")
            self.assertEqual(str(exc.exception), "Gemini returned an empty transcript.")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_sanitize_transcription_error_hides_sensitive_values(self):
        self.assertEqual(
            sanitize_transcription_error("invalid api key secret_value"),
            "Audio transcription provider authentication failed.",
        )


class TestTranscriptionEndpointTests(APITestCase):
    endpoint = "/api/transcriptions/test/"

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

    @patch("transcriptions.views.transcribe_audio_file")
    def test_approved_pharmacist_success(self, mock_transcribe):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559000",
        )
        mock_transcribe.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "transcript": "Take one tablet after food.",
        }
        self.client.force_authenticate(user)

        response = self.client.post(
            self.endpoint,
            {"audio": self.audio_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["provider"], "gemini")
        self.assertEqual(response.data["model"], "gemini-2.5-flash")
        self.assertEqual(response.data["transcript"], "Take one tablet after food.")
        mock_transcribe.assert_called_once()

    @patch("transcriptions.views.transcribe_audio_file")
    def test_pending_pharmacist_403(self, mock_transcribe):
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

    @patch("transcriptions.views.transcribe_audio_file")
    def test_rejected_pharmacist_403(self, mock_transcribe):
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

    @patch("transcriptions.views.transcribe_audio_file")
    def test_approved_patient_403(self, mock_transcribe):
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

    def test_missing_audio_400(self):
        user = self.create_pharmacist(
            approval_status=ApprovalStatusChoices.APPROVED,
            phone_number="5559004",
        )
        self.client.force_authenticate(user)

        response = self.client.post(self.endpoint, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("audio", response.data)

    @patch("transcriptions.views.transcribe_audio_file")
    def test_invalid_audio_type_400(self, mock_transcribe):
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

    @patch("transcriptions.views.transcribe_audio_file")
    def test_too_large_audio_400(self, mock_transcribe):
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

    @patch("transcriptions.views.transcribe_audio_file")
    def test_provider_failure_502(self, mock_transcribe):
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
        self.assertEqual(response.data["provider"], "gemini")
        self.assertEqual(response.data["error"], "provider unavailable")
