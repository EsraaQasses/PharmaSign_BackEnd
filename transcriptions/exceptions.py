class AudioTranscriptionError(Exception):
    """Raised when an external audio transcription provider fails."""

    def __init__(self, message, *, safe_message=None):
        super().__init__(message)
        self.safe_message = safe_message or sanitize_transcription_error(message)


def sanitize_transcription_error(message):
    text = str(message).strip()
    if not text:
        return "Audio transcription failed. Please try again."
    sensitive_markers = ("api_key", "api key", "authorization", "bearer ", "gsk_")
    if any(marker in text.lower() for marker in sensitive_markers):
        return "Audio transcription provider authentication failed."
    return text[:500]
