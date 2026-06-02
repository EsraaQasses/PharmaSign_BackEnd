class AIPoseGenerationError(Exception):
    """
    Custom exception raised when pose generation or communication with
    the external Gloss-to-Pose AI FastAPI service fails.
    """
    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or ""
