import logging
import requests
from django.conf import settings
from ai_integration.exceptions import AIPoseGenerationError

logger = logging.getLogger(__name__)


def generate_pose_from_gloss(
    gloss: str,
    return_format: str = "npy",
    return_video: bool = True,
    return_avatar: bool = True,
) -> dict:
    """
    Sends a request to the external FastAPI Gloss-to-Pose AI service to generate a pose.
    
    Args:
        gloss (str): The text gloss to generate the pose for.
        return_format (str): The format to return, defaults to 'npy'.
        return_video (bool): Whether the AI service should return a skeleton video.
        return_avatar (bool): Whether the AI service should return an avatar video.
        
    Returns:
        dict: The parsed successful JSON response from the AI service.
        
    Raises:
        AIPoseGenerationError: If validation, connection, or execution fails.
    """
    # 1. Validate input
    if not gloss or not gloss.strip():
        raise AIPoseGenerationError("Gloss text cannot be empty.")
        
    # 2. Build URL and headers
    url = f"{settings.AI_SERVICE_URL.rstrip('/')}/generate-pose"
    headers = {"Content-Type": "application/json"}
    
    if getattr(settings, "AI_SERVICE_API_KEY", ""):
        headers["X-API-Key"] = settings.AI_SERVICE_API_KEY
        
    payload = {
        "gloss": gloss.strip(),
        "return_format": return_format,
        "return_video": return_video,
        "return_avatar": return_avatar,
    }
    
    timeout = getattr(settings, "AI_SERVICE_TIMEOUT", 60)
    
    # 3. Perform request
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout connecting to AI pose generation service: {e}")
        raise AIPoseGenerationError("AI service request timed out.", details=str(e))
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error connecting to AI pose generation service: {e}")
        raise AIPoseGenerationError("AI service is currently unavailable.", details=str(e))
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request error in AI pose generation: {e}")
        raise AIPoseGenerationError("AI service request failed.", details=str(e))
        
    # 4. Handle response status
    if response.status_code != 200:
        logger.error(f"AI service returned non-200 status code: {response.status_code}. Response: {response.text}")
        raise AIPoseGenerationError(
            f"AI service failed with status code {response.status_code}.",
            details=response.text
        )
        
    # 5. Parse JSON and check payload-level success
    try:
        data = response.json()
    except ValueError as e:
        logger.error(f"Failed to parse AI service JSON response. Response: {response.text}")
        raise AIPoseGenerationError("AI service returned an invalid JSON response.", details=str(e))
        
    if not data.get("success", False):
        error_msg = data.get("error", "Pose generation succeeded but returned success=false.")
        logger.error(f"AI service reported failure: {error_msg}")
        raise AIPoseGenerationError(error_msg, details=str(data))
        
    return data


def check_ai_service_health() -> dict:
    """
    Checks the health of the external FastAPI AI service.
    
    Returns:
        dict: A dictionary indicating health status.
    """
    url = f"{settings.AI_SERVICE_URL.rstrip('/')}/health"
    timeout = 10  # shorter timeout for health check
    
    headers = {}
    if getattr(settings, "AI_SERVICE_API_KEY", ""):
        headers["X-API-Key"] = settings.AI_SERVICE_API_KEY
        
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            try:
                data = response.json()
                return {
                    "success": True,
                    "ai_service": data
                }
            except ValueError:
                return {
                    "success": True,
                    "ai_service": {
                        "status": "ok",
                        "raw_response": response.text
                    }
                }
        return {
            "success": False,
            "error": f"AI service returned health status code {response.status_code}",
            "details": response.text
        }
    except Exception as e:
        logger.error(f"AI health check exception: {e}")
        return {
            "success": False,
            "error": "AI service is unreachable",
            "details": str(e)
        }
