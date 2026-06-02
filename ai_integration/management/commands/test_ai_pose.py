from django.core.management.base import BaseCommand
from django.conf import settings
from ai_integration.services import generate_pose_from_gloss, check_ai_service_health
from ai_integration.exceptions import AIPoseGenerationError


class Command(BaseCommand):
    help = "Test connection and generation with the external FastAPI Gloss-to-Pose AI service."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gloss",
            type=str,
            default="دواء حبة الصبح قبل الاكل",
            help="The gloss text to send to the pose generator."
        )
        parser.add_argument(
            "--format",
            type=str,
            default="npy",
            choices=["npy", "json"],
            help="Response format requested."
        )

    def safe_write(self, msg, style_func=None):
        if style_func:
            msg = style_func(msg)
        try:
            self.stdout.write(msg)
        except UnicodeEncodeError:
            try:
                self.stdout.write(msg.encode("utf-8", errors="replace").decode("cp1252", errors="replace"))
            except Exception:
                self.stdout.write(msg.encode("ascii", errors="replace").decode("ascii"))

    def handle(self, *args, **options):
        gloss = options["gloss"]
        return_format = options["format"]

        self.safe_write("==================================================", self.style.WARNING)
        self.safe_write("       Gloss-to-Pose AI Service Test Tool       ", self.style.WARNING)
        self.safe_write("==================================================", self.style.WARNING)
        self.safe_write(f"Configured Service URL: {settings.AI_SERVICE_URL}")
        self.safe_write(f"Timeout: {settings.AI_SERVICE_TIMEOUT}s")
        self.safe_write(f"API Key present: {'Yes' if settings.AI_SERVICE_API_KEY else 'No'}\n")

        # 1. Health check test
        self.safe_write("--> Testing AI Service Health Check...")
        health = check_ai_service_health()
        if health.get("success", False):
            self.safe_write("[OK] AI Service Health Check passed!", self.style.SUCCESS)
            self.safe_write(f"     Details: {health.get('ai_service')}\n")
        else:
            self.safe_write("[FAIL] AI Service Health Check failed!", self.style.ERROR)
            self.safe_write(f"       Error: {health.get('error')}", self.style.ERROR)
            self.safe_write(f"       Details: {health.get('details')}\n", self.style.ERROR)

        # 2. Pose generation test
        self.safe_write(f"--> Requesting Pose Generation for gloss: '{gloss}'...")
        try:
            result = generate_pose_from_gloss(gloss=gloss, return_format=return_format)
            self.safe_write("[OK] Pose generation request succeeded!", self.style.SUCCESS)
            self.safe_write(f"     Success: {result.get('success')}")
            self.safe_write(f"     Gloss: {result.get('gloss')}")
            self.safe_write(f"     Pose Shape: {result.get('pose_shape')}")
            self.safe_write(f"     File Path: {result.get('file_path')}")
            self.safe_write(f"     Metadata: {result.get('metadata')}")
            
            if return_format == "json" and "pose" in result:
                pose_matrix = result["pose"]
                self.safe_write(f"     Pose Matrix present: Yes (coordinates: {len(pose_matrix) if pose_matrix else 0})")
                
            self.safe_write("\n[SUCCESS] AI integration is fully functional!", self.style.SUCCESS)
            
        except AIPoseGenerationError as e:
            self.safe_write("[FAIL] Pose generation request failed!", self.style.ERROR)
            self.safe_write(f"       Error: {e.message}", self.style.ERROR)
            if e.details:
                self.safe_write(f"       Details: {e.details}", self.style.ERROR)
        except Exception as e:
            self.safe_write("[ERROR] An unexpected internal error occurred!", self.style.ERROR)
            self.safe_write(f"        {str(e)}", self.style.ERROR)
            
        self.safe_write("==================================================", self.style.WARNING)
