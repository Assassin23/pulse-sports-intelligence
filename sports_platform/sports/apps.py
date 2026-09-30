"""
Sports app configuration.
"""
from django.apps import AppConfig


class SportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sports_platform.sports"
    label = "sports"
    verbose_name = "Sports Reference Data"
