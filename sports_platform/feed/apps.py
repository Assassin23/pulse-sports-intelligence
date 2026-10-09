"""
Feed Django app configuration.
"""
from django.apps import AppConfig


class FeedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sports_platform.feed"
    label = "feed"
    verbose_name = "Personalized Feed"
