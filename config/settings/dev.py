"""Development settings: runserver on plain-HTTP localhost."""

from .base import *  # noqa: F403

# runserver speaks plain HTTP; secure-only cookies would never come back.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Do not override EMAIL_BACKEND here: base.py forces the console backend
# under DEMO_MODE and that must not be bypassed.
