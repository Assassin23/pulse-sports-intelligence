"""
Local development settings.
Reads from .env file in project root.
"""
from pathlib import Path

import environ

from .base import *  # noqa: F401, F403

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Load .env file if it exists (local dev)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))
else:
    # Fall back to .env.example values for first-time setup
    environ.Env.read_env(str(BASE_DIR / ".env.example"))

DEBUG = True

# Allow all hosts locally
ALLOWED_HOSTS = ["*"]

# ─── Email backend (console for dev) ─────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ─── Django Extensions ────────────────────────────────────────────────────────
INSTALLED_APPS = INSTALLED_APPS + ["django_extensions"]  # noqa: F405

# ─── Disable throttling in local dev ─────────────────────────────────────────
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
}
