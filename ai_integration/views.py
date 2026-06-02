import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from ai_integration.serializers import AIPoseRequestSerializer
from ai_integration.services import generate_pose_from_gloss, check_ai_service_health
from ai_integration.exceptions import AIPoseGenerationError

logger = logging.getLogger(__name__)


class AIPoseGenerationView(APIView):
    """
    Endpoint to request Gloss-to-Pose generation from the external AI FastAPI service.
    
    POST /api/ai/generate-pose/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AIPoseRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": "Validation failed",
                    "details": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
            
        gloss = serializer.validated_data["gloss"]
        return_format = serializer.validated_data["return_format"]
        
        if return_format == "json":
            logger.warning(
                "User requested 'json' return format for pose generation. "
                "Warning: JSON format can contain a very large coordinate matrix and cause high network overhead."
            )
            
        try:
            result = generate_pose_from_gloss(gloss=gloss, return_format=return_format)
            
            # Construct a clean response
            response_data = {
                "success": True,
                "gloss": result.get("gloss", gloss),
                "pose_shape": result.get("pose_shape"),
                "file_path": result.get("file_path"),
                "metadata": result.get("metadata", {})
            }
            
            # If the user explicitly requested json and it is in the response, forward it.
            if return_format == "json" and "pose" in result:
                response_data["pose"] = result["pose"]
                
            return Response(response_data, status=status.HTTP_200_OK)
            
        except AIPoseGenerationError as e:
            logger.error(f"Gloss-to-pose generation failed: {e.message}")
            return Response(
                {
                    "success": False,
                    "error": "AI service unavailable or failed",
                    "details": e.message
                },
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            logger.exception("Unexpected error occurred during AI pose generation.")
            return Response(
                {
                    "success": False,
                    "error": "Internal server error during pose generation",
                    "details": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AIServiceHealthView(APIView):
    """
    Endpoint to check the health status of the external AI service.
    
    GET /api/ai/health/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        health_status = check_ai_service_health()
        
        if health_status.get("success", False):
            return Response(health_status, status=status.HTTP_200_OK)
        else:
            return Response(
                {
                    "success": False,
                    "error": "AI pose service is unhealthy or unreachable",
                    "details": health_status.get("error", "Unknown error")
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
