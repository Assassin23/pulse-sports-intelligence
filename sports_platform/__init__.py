"""
Sports Platform Django Application.
"""
# Ensure the Celery app is loaded whenever Django starts so that
# @shared_task decorators bind to it.
from sports_platform.celery import app as celery_app

__all__ = ("celery_app",)
