"""
Base settings for CAMS.

Every environment-specific value is read from .env via django-environ.
dev.py (and, after the demo, prod.py) import from here.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ----------------------------------------------------------------- identity
# Must be set before the first makemigrations. Swapping the user model once
# tables exist is a manual, painful migration. docs/02_DATA_MODEL.md.
AUTH_USER_MODEL = "accounts.User"

# --------------------------------------------------------------------- core
SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# -------------------------------------------------------------- institution
INSTITUTION_NAME = env("INSTITUTION_NAME")
INSTITUTION_CODE = env("INSTITUTION_CODE")

# ---------------------------------------------------------------- demo mode
# A safety feature, not a convenience: banner on every page, specimen line on
# every generated order, no real email. docs/08_DEMO_DATA.md §1.
DEMO_MODE = env.bool("DEMO_MODE", default=False)

# ------------------------------------------------------------- applications
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "committees",
    "assignments",
    "orders",
    "audit",
    "core",
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
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.institution",
            ],
        },
    },
]

# ----------------------------------------------------------------- database
# SQLite during the demo sprint. PostgreSQL 18 is one DATABASE_URL change away.
# select_for_update is a no-op on SQLite: debt item 1, docs/09_LOCAL_POSTGRES.md.
DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    _sqlite_name = DATABASES["default"]["NAME"]
    if _sqlite_name != ":memory:" and not Path(_sqlite_name).is_absolute():
        DATABASES["default"]["NAME"] = BASE_DIR / _sqlite_name

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------- auth
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"

ADMIN_URL = env("ADMIN_URL")

# ------------------------------------------------------ sessions & headers
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# ---------------------------------------------------- internationalisation
# Day-first date formats. Strings are wrapped for a later Gujarati translation.
LANGUAGE_CODE = "en-gb"
TIME_ZONE = env("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------ static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ------------------------------------------------------------------ media
# Uploaded templates, the Principal's signature and generated orders.
# Never routed in urls.py, never served by the web server, never in
# STATICFILES_DIRS. Reachable only through permission-checked FileResponse
# views. docs/03_SECURITY.md §3.
MEDIA_ROOT = BASE_DIR / env("MEDIA_ROOT", default="media/")
MEDIA_URL = "/media/"

# ------------------------------------------------------------------ email
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = env("SERVER_EMAIL")

if DEMO_MODE:
    # Forced regardless of .env: a demo must never mail a real faculty address.
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
