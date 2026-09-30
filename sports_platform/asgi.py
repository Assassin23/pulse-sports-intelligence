"""
ASGI config for Sports Platform.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sports_platform.settings.local")
application = get_asgi_application()
