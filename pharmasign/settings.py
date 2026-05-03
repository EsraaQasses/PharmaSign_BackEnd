import os
from pathlib import Path
from decouple import config
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me-in-production")


def env_to_bool(value):
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "debug"}:
        return True
    if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
        return False
    return bool(value)


def env_to_list(value):
    return tuple(part.strip().lower() for part in str(value).split(",") if part.strip())


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_to_bool(config("DEBUG", default="True"))

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
]

LOCAL_APPS = [
    "common",
    "accounts",
    "organizations",
    "patients",
    "pharmacies",
    "prescriptions",
    "transcriptions",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pharmasign.urls"

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default=(
        "http://localhost:8081,"
        "http://localhost:8082,"
        "http://localhost:19006,"
        "http://127.0.0.1:8081,"
        "http://127.0.0.1:8082,"
        "http://127.0.0.1:19006"
    ),
    cast=lambda value: [
        origin.strip() for origin in value.split(",") if origin.strip()
    ],
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "pharmasign.wsgi.application"

# Database - PostgreSQL primary, SQLite fallback for dev
DB_NAME = config("DB_NAME", default="db.sqlite3")
if DB_NAME != "db.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = config("MEDIA_URL", "/media/")
MEDIA_ROOT = BASE_DIR / config("MEDIA_ROOT", "media")
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750
PHARMASIGN_MAX_IMAGE_UPLOAD_BYTES = config(
    "PHARMASIGN_MAX_IMAGE_UPLOAD_BYTES",
    default=5 * 1024 * 1024,
    cast=int,
)
PHARMASIGN_MAX_AUDIO_UPLOAD_BYTES = config(
    "PHARMASIGN_MAX_AUDIO_UPLOAD_BYTES",
    default=15 * 1024 * 1024,
    cast=int,
)
PHARMASIGN_MAX_VIDEO_UPLOAD_BYTES = config(
    "PHARMASIGN_MAX_VIDEO_UPLOAD_BYTES",
    default=50 * 1024 * 1024,
    cast=int,
)
PHARMASIGN_ALLOWED_IMAGE_EXTENSIONS = env_to_list(
    config(
        "PHARMASIGN_ALLOWED_IMAGE_EXTENSIONS",
        default=".jpg,.jpeg,.png,.webp",
    )
)
PHARMASIGN_ALLOWED_AUDIO_EXTENSIONS = env_to_list(
    config(
        "PHARMASIGN_ALLOWED_AUDIO_EXTENSIONS",
        default=".mp3,.mpeg,.wav,.wave,.ogg,.oga,.opus,.webm,.m4a,.mp4,.aac,.flac,.amr,.3gp,.3gpp",
    )
)
PHARMASIGN_ALLOWED_VIDEO_EXTENSIONS = env_to_list(
    config(
        "PHARMASIGN_ALLOWED_VIDEO_EXTENSIONS",
        default=".mp4,.webm,.mov",
    )
)
PHARMASIGN_ALLOWED_IMAGE_CONTENT_TYPES = env_to_list(
    config(
        "PHARMASIGN_ALLOWED_IMAGE_CONTENT_TYPES",
        default="image/jpeg,image/png,image/webp",
    )
)
PHARMASIGN_ALLOWED_AUDIO_CONTENT_TYPES = env_to_list(
    config(
        "PHARMASIGN_ALLOWED_AUDIO_CONTENT_TYPES",
        default=(
            "audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/wave,"
            "audio/vnd.wave,audio/ogg,audio/opus,audio/webm,audio/mp4,"
            "audio/x-m4a,audio/aac,audio/flac,audio/x-flac,audio/amr,"
            "audio/3gpp,video/3gpp,application/ogg,application/octet-stream"
        ),
    )
)
PHARMASIGN_ALLOWED_VIDEO_CONTENT_TYPES = env_to_list(
    config(
        "PHARMASIGN_ALLOWED_VIDEO_CONTENT_TYPES",
        default="video/mp4,video/webm,video/quicktime",
    )
)
TRANSCRIPTION_PROVIDER = "gemini"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_SIGN_MODEL = os.getenv("GEMINI_SIGN_MODEL", GEMINI_MODEL)
MAX_AUDIO_UPLOAD_SIZE_MB = config("MAX_AUDIO_UPLOAD_SIZE_MB", default=10, cast=int)

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF Configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.ApprovalAwareJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# JWT Configuration
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        hours=config("JWT_ACCESS_TOKEN_LIFETIME", default=5, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
}
