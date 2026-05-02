from django.urls import path

from .views import TestGroqTranscriptionView


app_name = "transcriptions"

urlpatterns = [
    path(
        "test-groq/",
        TestGroqTranscriptionView.as_view(),
        name="test_groq",
    ),
]
