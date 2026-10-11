"""Settings for the test suite: fast, isolated, and never touching real media."""

import tempfile

from .base import *  # noqa: F403

DEBUG = False

# Tests must never write into the real media directory (docs/05_TESTING.md §1).
MEDIA_ROOT = tempfile.mkdtemp(prefix="cams-test-media-")

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Demo mode is exercised explicitly with override_settings where it matters.
DEMO_MODE = True

# Hashing dominates the runtime of auth tests; correctness is unaffected.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
