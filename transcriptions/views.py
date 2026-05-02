import os
import tempfile
from pathlib import Path

from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.choices import ApprovalStatusChoices, RoleChoices

from .services import (
    GROQ_TRANSCRIPTION_MODEL,
    TranscriptionError,
    transcribe_audio_file_with_groq,
)


SUPPORTED_TEST_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/mp4",
    "audio/m4a",
    "audio/aac",
    "audio/ogg",
}
MAX_TEST_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024


class TestGroqTranscriptionView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _permission_denied_response(self, detail):
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

    def _validate_user(self, user):
        if user.approval_status == ApprovalStatusChoices.PENDING:
            return self._permission_denied_response(
                "حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة."
            )
        if user.approval_status == ApprovalStatusChoices.REJECTED:
            return self._permission_denied_response(
                "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة."
            )
        if user.approval_status != ApprovalStatusChoices.APPROVED:
            return self._permission_denied_response("User account is not approved.")
        if user.role != RoleChoices.PHARMACIST:
            return self._permission_denied_response(
                "Only approved pharmacists can transcribe audio."
            )
        return None

    def _validate_audio(self, audio):
        if audio is None:
            return Response(
                {"audio": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = (getattr(audio, "content_type", "") or "").lower()
        if content_type not in SUPPORTED_TEST_AUDIO_CONTENT_TYPES:
            return Response(
                {"audio": ["Unsupported audio file type."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if audio.size > MAX_TEST_AUDIO_UPLOAD_BYTES:
            return Response(
                {"audio": ["Audio file size must not exceed 25MB."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def _temporary_suffix(self, audio):
        suffix = Path(getattr(audio, "name", "") or "").suffix
        if suffix:
            return suffix
        return ".audio"

    def post(self, request):
        permission_response = self._validate_user(request.user)
        if permission_response:
            return permission_response

        audio = request.FILES.get("audio")
        validation_response = self._validate_audio(audio)
        if validation_response:
            return validation_response

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=self._temporary_suffix(audio),
            ) as temp_file:
                temp_path = temp_file.name
                for chunk in audio.chunks():
                    temp_file.write(chunk)

            transcript = transcribe_audio_file_with_groq(temp_path)
        except TranscriptionError as exc:
            return Response(
                {
                    "status": "failed",
                    "provider": "groq",
                    "error": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        return Response(
            {
                "status": "completed",
                "provider": "groq",
                "model": GROQ_TRANSCRIPTION_MODEL,
                "transcript": transcript,
            }
        )
