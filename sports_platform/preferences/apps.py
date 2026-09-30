"""
Preferences app configuration.
"""
from django.apps import AppConfig


class PreferencesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sports_platform.preferences"
    label = "preferences"
    verbose_name = "User Preferences"
