from django.urls import path
from ai_integration.views import AIPoseGenerationView, AIServiceHealthView

urlpatterns = [
    path("generate-pose/", AIPoseGenerationView.as_view(), name="ai-generate-pose"),
    path("health/", AIServiceHealthView.as_view(), name="ai-health"),
]
