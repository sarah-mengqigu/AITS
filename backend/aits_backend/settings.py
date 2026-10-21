"""Django settings for the AITS v2 platform.

Everything is environment driven so the same code base runs:
  * dev / test  -> SQLite + in-memory cache + in-memory channel layer + eager Celery
  * production   -> PostgreSQL + Redis (cache / broker / channel layer)

See ``docs/ARCHITECTURE.md`` for the contract every module must respect.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# env helpers
# ---------------------------------------------------------------------------
def env(key, default=None):
    value = os.environ.get(key)
    return default if value is None or value == "" else value


def env_bool(key, default=False):
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(key, default):
    try:
        return int(env(key, default))
    except (TypeError, ValueError):
        return default


def env_list(key, default=None):
    value = env(key)
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# environment mode
# ---------------------------------------------------------------------------
AITS_ENV = env("AITS_ENV", "dev").lower()  # dev | test | prod
AITS_TESTING = AITS_ENV == "test" or "test" in sys.argv or "pytest" in sys.modules

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-aits-secret-key-change-me")
DEBUG = env_bool("DEBUG", AITS_ENV != "prod")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["*"] if DEBUG else ["localhost", "127.0.0.1"])

FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", "http://127.0.0.1:5173")

# ---------------------------------------------------------------------------
# applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "django_celery_beat",
    "drf_spectacular",
    "channels",
    # AITS business apps (9)
    "apps.common",
    "apps.users",
    "apps.projects",
    "apps.api_testing",
    "apps.web_testing",
    "apps.app_testing",
    "apps.performance",
    "apps.ai_core",
    "apps.scheduled_tasks",
    "apps.notifications",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aits_backend.urls"

TEMPLATES = [
    {
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
    },
]

WSGI_APPLICATION = "aits_backend.wsgi.application"
ASGI_APPLICATION = "aits_backend.asgi.application"

# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------
if env("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "aits"),
            "USER": env("DB_USER", "aits"),
            "PASSWORD": env("DB_PASSWORD", "aits"),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
            "OPTIONS": {"timeout": 20},
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# auth / JWT
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 600)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 1)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": env_int("API_PAGE_SIZE", 20),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.api.api_exception_handler.custom_exception_handler",
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AITS API",
    "DESCRIPTION": "AITS v2 - AI-empowered Intelligent Testing System",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# cache / channel layer (Redis in prod, in-memory otherwise)
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6379/0")
# Redis is only required in production; dev/test default to in-memory so the
# platform boots without any external service. Set USE_REDIS=1 to force it.
USE_REDIS = env_bool("USE_REDIS", AITS_ENV == "prod")

if USE_REDIS:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "MAX_CONNECTIONS": 50,
                "SOCKET_CONNECT_TIMEOUT": 5,
                "SOCKET_TIMEOUT": 5,
            },
            "KEY_PREFIX": "aits",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL], "capacity": 100, "expiry": 60,
                       "group_expiry": 86400},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "aits-locmem",
        }
    }
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL if USE_REDIS else "memory://")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL if USE_REDIS else "cache+memory://")
# Without a real broker (no Redis in dev/test) tasks run inline so that
# executions complete synchronously. Production uses the Redis broker + worker.
CELERY_TASK_ALWAYS_EAGER = env_bool(
    "CELERY_TASK_ALWAYS_EAGER", AITS_TESTING or not USE_REDIS
)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = env("CELERY_TIMEZONE", "Asia/Shanghai")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 3600)

# ---------------------------------------------------------------------------
# CORS / CSRF
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    [FRONTEND_BASE_URL, "http://localhost:5173", "http://127.0.0.1:5173"],
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [FRONTEND_BASE_URL])

# ---------------------------------------------------------------------------
# internationalisation / static
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = env("TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
ALLURE_RESULTS_ROOT = Path(env("ALLURE_RESULTS_ROOT", str(MEDIA_ROOT / "allure-results")))
REPORT_ROOT = Path(env("REPORT_ROOT", str(MEDIA_ROOT / "reports")))

FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"],
                               "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# AITS specific runtime switches
# ---------------------------------------------------------------------------
# simulated -> deterministic in-process execution (used for tests / demos)
# real      -> spawn Playwright / Locust / HttpRunner subprocesses
AITS_EXECUTION_MODE = env("AITS_EXECUTION_MODE", "simulated").lower()
AITS_MAX_AGENT_STEPS = env_int("AITS_MAX_AGENT_STEPS", 12)
# Agent orchestration engine: auto (LangGraph when installed) | builtin | langgraph
AITS_AGENT_ENGINE = env("AITS_AGENT_ENGINE", "auto").strip().lower()
# LLM client backend: auto (LangChain when installed) | langchain | http
AITS_LLM_BACKEND = env("AITS_LLM_BACKEND", "auto").strip().lower()
# langsmith is a transitive dependency of langgraph; keep it offline by default.
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

# Mobile (Sonic) integration
SONIC_BASE_URL = env("SONIC_BASE_URL", "")
SONIC_API_PREFIX = env("SONIC_API_PREFIX", "/server/api")
SONIC_USERNAME = env("SONIC_USERNAME", "")
SONIC_PASSWORD = env("SONIC_PASSWORD", "")
SONIC_TOKEN = env("SONIC_TOKEN", "")
SONIC_PROJECT_ID = env("SONIC_PROJECT_ID", "")
SONIC_TIMEOUT = env_int("SONIC_TIMEOUT", 15)

# Observability
PROMETHEUS_SD_AUTO_UPDATE = env_bool("PROMETHEUS_SD_AUTO_UPDATE", True)
PROMETHEUS_TARGETS_FILE = env(
    "PROMETHEUS_TARGETS_FILE",
    str(BASE_DIR / "aits_monitor" / "prometheus" / "targets.json"),
)
WINDOWS_EXPORTER_PORT = env_int("WINDOWS_EXPORTER_PORT", 9182)
GRAFANA_AI_NOTIFY_RECEIVER_ID = env("GRAFANA_AI_NOTIFY_RECEIVER_ID", "")
GRAFANA_AI_NOTIFY_RECEIVER_NAME_KEYWORD = env(
    "GRAFANA_AI_NOTIFY_RECEIVER_NAME_KEYWORD", "AI测试部门群"
)

# AI defaults (DB config wins at runtime)
AI_REQUEST_TIMEOUT = env_int("AI_REQUEST_TIMEOUT", 120)
AI_MOCK_MODE = env_bool("AI_MOCK_MODE", AITS_TESTING)

# Email fallback (EmailConfig in DB wins)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "aits@example.com")

# Absolute URL helper for notifications
SITE_URL = env("SITE_URL", FRONTEND_BASE_URL.rstrip("/"))
