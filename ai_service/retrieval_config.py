from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SIGN_RETRIEVAL_CLIPS_ROOT = (
    BASE_DIR / "external_data" / "sign_retrieval"
)

AVATAR_VIDEO_OUTPUT_DIR = (
    BASE_DIR / "media" / "generated" / "avatar_videos"
)

AVATAR_VIDEO_MEDIA_PREFIX = "/media/generated/avatar_videos"

DEFAULT_AVATAR_VIDEO_FILENAME = "generated_avatar.mp4"
