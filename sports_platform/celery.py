"""
Celery application for the Sports Intelligence Platform.

Started by docker-compose as:
    celery -A sports_platform worker -l INFO -Q ingestion,default
    celery -A sports_platform beat   -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

Configuration is read from Django settings using the ``CELERY_`` prefix.
The periodic schedule lives in ``settings.CELERY_BEAT_SCHEDULE``; the
DatabaseScheduler syncs it into django_celery_beat tables on startup so it can
also be tweaked from the Django admin.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sports_platform.settings.local")

app = Celery("sports_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Discovers <app>/tasks.py for every app in INSTALLED_APPS (e.g. ingestion.tasks)
app.autodiscover_tasks()
