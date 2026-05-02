from django.urls import path

from .views import TestTranscriptionView


app_name = "transcriptions"

urlpatterns = [
    path(
        "test/",
        TestTranscriptionView.as_view(),
        name="test_transcription",
    ),
]
