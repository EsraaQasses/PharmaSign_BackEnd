import logging
import os
import tempfile
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.choices import ApprovalStatusChoices, RoleChoices

from .services import TranscriptionError, transcribe_audio_file


logger = logging.getLogger(__name__)

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
PENDING_APPROVAL_DETAIL = (
    "حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة."
)
REJECTED_APPROVAL_DETAIL = "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة."


class TestTranscriptionView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _permission_denied_response(self, detail):
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

    def _validate_user(self, user):
        if user.approval_status == ApprovalStatusChoices.PENDING:
            return self._permission_denied_response(PENDING_APPROVAL_DETAIL)
        if user.approval_status == ApprovalStatusChoices.REJECTED:
            return self._permission_denied_response(REJECTED_APPROVAL_DETAIL)
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
        return suffix or ".audio"

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

            result = transcribe_audio_file(
                temp_path,
                mime_type=(getattr(audio, "content_type", None) or None),
            )
        except TranscriptionError as exc:
            if settings.DEBUG:
                logger.exception("Standalone transcription provider failed.")
            return Response(
                {
                    "status": "failed",
                    "provider": "gemini",
                    "error": exc.safe_message,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        return Response(
            {
                "status": "completed",
                "provider": result["provider"],
                "model": result["model"],
                "transcript": result["transcript"],
            }
        )
