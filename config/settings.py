from pathlib import Path
from datetime import timedelta
import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------
# Env
# -----------------------------
env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# -----------------------------
# Core
# -----------------------------
SECRET_KEY = env("SECRET_KEY", default="unsafe-dev")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", default="").split(",") if h.strip()]
LANGUAGE_CODE = "es"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ASGI (para Uvicorn/Gunicorn-uvicorn)
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

# -----------------------------
# Apps
# -----------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",     

    # Terceros
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "pgvector.django",            

    # Apps
    "staff_whitelist",
    "accounts_signup",
    "accounts_auth",
    "accounts_password",
    "documents",
    "search.apps.SearchConfig",
    "ranking_adaptive"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],   
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

# -----------------------------
# Base de datos
# -----------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 60,  # pooling simple
    }
}

# -----------------------------
# Cache / Sesiones (Redis)
# -----------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "TIMEOUT": 300,  # 5 min
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
THROTTLE_CACHE_ALIAS = "default"

# -----------------------------
# DRF / OpenAPI (drf-spectacular)
# -----------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "otp_ip": "5/minute",
        "otp_email": "3/hour",
        "resend_ip": "3/minute",
        "resend_email": "2/hour",
        "status_ip": "30/minute",
        "status_email": "10/minute",
        "login_ip": "10/minute",
        "login_email": "5/minute",
        "pwd_reset_ip": "5/minute",
        "pwd_reset_email": "3/hour",
        "pwd_resend_ip": "3/minute",
        "pwd_resend_email": "2/hour",
        "pwd_status_ip": "30/minute",
        "pwd_status_email": "10/minute",
        "search_ask_burst": "10/minute",
        "search_ask_sustained": "500/day",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Alexandria API",
    "DESCRIPTION": "API de autenticación, ingestión de documentos, búsqueda y chat RAG.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api",
    "COMPONENT_SPLIT_REQUEST": True,
}

# -----------------------------
# JWT
# -----------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}

# -----------------------------
# Email
# -----------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default=None)
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default=None)
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default=None)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@example.com")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# -----------------------------
# Branding
# -----------------------------
BRAND_NAME = env("BRAND_NAME", default="Sanjinés & Asociados")
BRAND_PRIMARY_COLOR = env("BRAND_PRIMARY_COLOR", default="#023f66")
BRAND_LOGO_URL = env("BRAND_LOGO_URL", default="")
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

# -----------------------------
# Archivos estáticos/media
# -----------------------------
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------
# Celery (Broker/Resultados desde Redis)
# -----------------------------
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/1")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
# (Opcional) colas por defecto; puedes configurarlas también en celery.py
CELERY_TASK_DEFAULT_QUEUE = "default"
# Usa -Q ingestion,extraction,chunking,embedding al arrancar el worker

# -----------------------------
# S3 / MinIO
# -----------------------------
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default=None)          # ej. http://minio:9000
S3_BUCKET_NAME = env("S3_BUCKET_NAME", default=None)            # ej. alexandria
S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID", default=None)
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY", default=None)
S3_REGION = env("S3_REGION", default="us-east-1")
S3_ADDRESSING_STYLE = env("S3_ADDRESSING_STYLE", default="path")  # path|auto
S3_USE_SSL = env.bool("S3_USE_SSL", default=False)
MINIO_PRESIGN_EXPIRES = env.int("MINIO_PRESIGN_EXPIRES", default=300)

# -----------------------------
# Flags / Reglas Whitelist
# -----------------------------
WHITELIST_DISABLE_SUPERUSERS = env.bool("WHITELIST_DISABLE_SUPERUSERS", default=False)
WHITELIST_REVOKE_REFRESH_ON_DEACTIVATE = env.bool("WHITELIST_REVOKE_REFRESH_ON_DEACTIVATE", default=True)

# -----------------------------
# RAG / Búsqueda (parámetros base)
# -----------------------------
RAG_EMBEDDINGS_PROVIDER = env("RAG_EMBEDDINGS_PROVIDER", default="local")   # local|openai|hf
EMBEDDINGS_MODEL = env("EMBEDDINGS_MODEL", default="multilingual-e5-large")
RERANKER_MODEL = env("RERANKER_MODEL", default="BAAI/bge-reranker-v2-m3")
HYBRID_ALPHA = env.float("HYBRID_ALPHA", default=0.6)       # peso de semántica vs. léxica
SEARCH_TOP_K = env.int("SEARCH_TOP_K", default=50)
RERANK_TOP_N = env.int("RERANK_TOP_N", default=12)
FUSION_CANDIDATES = env.int("FUSION_CANDIDATES", default=100)
RERANK_CANDIDATES = env.int("RERANK_CANDIDATES", default=100)
RERANK_BATCH_SIZE = env.int("RERANK_BATCH_SIZE", default=32) 
RRF_K = 60.0
ENABLE_RERANK = env.bool("ENABLE_RERANK", default=True)
OPENAI_API_KEY = env("OPENAI_API_KEY", default=None)
HF_API_TOKEN = env("HF_API_TOKEN", default=None)

# Pesos de la fórmula
RANK_WEIGHTS = {
    "W_CE": 1.0,
    "W_VIG": 0.75,
    "W_ORG": 0.35,
    "W_ID": 0.90,
    "W_T": 0.25,
}

# Jerarquía de órgano
ORG_WEIGHTS = {
    "tcp": 1.0,
    "tsj": 0.8,
    "sala": 0.6,
    "ley": 0.7,
    "cpe": 0.9,
    "otros": 0.3,
}

# Recencia (solo jurisprudencia)
RECENCY_SOURCES = {"tcp", "tsj", "sala"}
RECENCY_HALFLIFE_DAYS = 4 * 365

ADAPTIVE_RANKING_ENABLED = True
ADAPTIVE_RANKING_ALPHA = 1.0  

CELERY_BEAT_SCHEDULE = {
    "train-signal-weights-weekly": {
        "task": "ranking_adaptive.tasks.train_signal_weights",
        "schedule": crontab(hour=3, minute=0, day_of_week="sun"),  # Domingos 03:00
        "args": (),   # puedes pasar días/lr/steps si quieres
    },
}