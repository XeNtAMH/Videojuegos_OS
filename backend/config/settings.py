import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY debe configurarse fuera de desarrollo.")
    SECRET_KEY = "dev-only-change-this-secret-key-before-deploying-please"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "backend.store",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "backend.config.wsgi.application"
ASGI_APPLICATION = "backend.config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=60,
            conn_health_checks=True,
            ssl_require=not DEBUG,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "store.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Havana"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "media/"

supabase_storage_settings = {
    "access_key": os.getenv("SUPABASE_S3_ACCESS_KEY_ID"),
    "secret_key": os.getenv("SUPABASE_S3_SECRET_ACCESS_KEY"),
    "bucket_name": os.getenv("SUPABASE_STORAGE_BUCKET"),
    "endpoint_url": os.getenv("SUPABASE_S3_ENDPOINT_URL"),
    "region_name": os.getenv("SUPABASE_S3_REGION"),
}
if any(supabase_storage_settings.values()):
    missing_storage_settings = [
        name
        for name, value in supabase_storage_settings.items()
        if not value
    ]
    if missing_storage_settings:
        raise ImproperlyConfigured(
            "Faltan variables de Supabase Storage: "
            + ", ".join(missing_storage_settings)
        )
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **supabase_storage_settings,
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": True,
            "signature_version": "s3v4",
            "addressing_style": "path",
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173"
    ).split(",")
    if origin.strip()
]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "backend.store.email_backend.BrevoEmailBackend"
    if os.getenv("BREVO_API_KEY")
    else "django.core.mail.backends.smtp.EmailBackend",
)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "Tienda Gamer <pedroglzzz08@gmail.com>"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "be14bc001@smtp-brevo.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

if not DEBUG:
    if not DATABASE_URL:
        raise ImproperlyConfigured("DATABASE_URL es obligatorio fuera de desarrollo.")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 15_552_000
    SECURE_CONTENT_TYPE_NOSNIFF = True
