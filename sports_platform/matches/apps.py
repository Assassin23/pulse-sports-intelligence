"""
Matches Django app configuration.
"""
from django.apps import AppConfig


class MatchesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sports_platform.matches"
    label = "matches"
    verbose_name = "Matches"
