"""
Local development settings.
Reads from .env file in project root.
"""
import os
from pathlib import Path

import environ

from .base import *  # noqa: F401, F403

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Only re-read .env if running on host machine outside container
if not (os.environ.get("IN_DOCKER") == "true" or Path("/.dockerenv").exists()):
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        environ.Env.read_env(str(env_file), overwrite=True)
    else:
        environ.Env.read_env(str(BASE_DIR / ".env.example"), overwrite=True)

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

# ─── CORS in local dev ────────────────────────────────────────────────────────
# Allow any localhost or 127.0.0.1 port (e.g. 5173, 8081, 3000)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
]
