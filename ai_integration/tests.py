from unittest.mock import patch
import requests
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import RoleChoices
from ai_integration.services import generate_pose_from_gloss, check_ai_service_health
from ai_integration.exceptions import AIPoseGenerationError


class AIPoseServiceUnitTests(APITestCase):
    """
    Unit tests for Gloss-to-Pose AI integration services.
    """

    @patch("requests.post")
    def test_generate_pose_success(self, mock_post):
        # Mock successful response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "success": True,
            "gloss": "دواء حبة الصبح قبل الاكل",
            "pose_shape": [128, 576],
            "file_path": "generated_outputs/gen_123.npy",
            "metadata": {"model": "v4_bounded", "device": "cuda"}
        }

        result = generate_pose_from_gloss("دواء حبة الصبح قبل الاكل")
        self.assertTrue(result["success"])
        self.assertEqual(result["pose_shape"], [128, 576])
        self.assertEqual(result["file_path"], "generated_outputs/gen_123.npy")
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertTrue(payload["return_video"])
        self.assertTrue(payload["return_avatar"])

    def test_generate_pose_empty_gloss(self):
        with self.assertRaises(AIPoseGenerationError) as ctx:
            generate_pose_from_gloss("")
        self.assertEqual(ctx.exception.message, "Gloss text cannot be empty.")

    @patch("requests.post")
    def test_generate_pose_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
        with self.assertRaises(AIPoseGenerationError) as ctx:
            generate_pose_from_gloss("test")
        self.assertEqual(ctx.exception.message, "AI service request timed out.")

    @patch("requests.post")
    def test_generate_pose_connection_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Failed to connect")
        with self.assertRaises(AIPoseGenerationError) as ctx:
            generate_pose_from_gloss("test")
        self.assertEqual(ctx.exception.message, "AI service is currently unavailable.")

    @patch("requests.post")
    def test_generate_pose_non_200_status(self, mock_post):
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"
        with self.assertRaises(AIPoseGenerationError) as ctx:
            generate_pose_from_gloss("test")
        self.assertIn("failed with status code 500", ctx.exception.message)

    @patch("requests.post")
    def test_generate_pose_payload_failure(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "success": False,
            "error": "Model initialization failed."
        }
        with self.assertRaises(AIPoseGenerationError) as ctx:
            generate_pose_from_gloss("test")
        self.assertEqual(ctx.exception.message, "Model initialization failed.")

    @patch("requests.get")
    def test_health_check_success(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "status": "ok",
            "model_loaded": True,
            "device": "cuda"
        }
        
        result = check_ai_service_health()
        self.assertTrue(result["success"])
        self.assertEqual(result["ai_service"]["status"], "ok")
        self.assertTrue(result["ai_service"]["model_loaded"])


class AIPoseAPIViewTests(APITestCase):
    """
    API endpoint tests for AI integration views.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="test.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST
        )

    def test_endpoints_require_authentication(self):
        # 1. generate pose
        response = self.client.post(reverse("ai-generate-pose"), {"gloss": "test"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. health check
        response = self.client.get(reverse("ai-health"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("ai_integration.views.generate_pose_from_gloss")
    def test_generate_pose_api_success(self, mock_service):
        self.client.force_authenticate(self.user)
        mock_service.return_value = {
            "success": True,
            "gloss": "دواء حبة الصبح قبل الاكل",
            "pose_shape": [128, 576],
            "file_path": "generated_outputs/gen_123.npy",
            "metadata": {"model": "v4"}
        }

        response = self.client.post(
            reverse("ai-generate-pose"),
            {"gloss": "دواء حبة الصبح قبل الاكل", "return_format": "npy"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["file_path"], "generated_outputs/gen_123.npy")
        self.assertEqual(response.data["pose_shape"], [128, 576])

    def test_generate_pose_api_validation_failed(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse("ai-generate-pose"),
            {"gloss": ""},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("gloss", response.data["details"])

    @patch("ai_integration.views.generate_pose_from_gloss")
    def test_generate_pose_api_service_failed(self, mock_service):
        self.client.force_authenticate(self.user)
        mock_service.side_effect = AIPoseGenerationError("AI service is currently unavailable.")

        response = self.client.post(
            reverse("ai-generate-pose"),
            {"gloss": "دواء حبة"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"], "AI service unavailable or failed")
        self.assertEqual(response.data["details"], "AI service is currently unavailable.")

    @patch("ai_integration.views.check_ai_service_health")
    def test_health_api_success(self, mock_service):
        self.client.force_authenticate(self.user)
        mock_service.return_value = {
            "success": True,
            "ai_service": {"status": "ok"}
        }

        response = self.client.get(reverse("ai-health"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["ai_service"]["status"], "ok")

    @patch("ai_integration.views.check_ai_service_health")
    def test_health_api_unhealthy(self, mock_service):
        self.client.force_authenticate(self.user)
        mock_service.return_value = {
            "success": False,
            "error": "AI service is unreachable"
        }

        response = self.client.get(reverse("ai-health"))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"], "AI pose service is unhealthy or unreachable")
