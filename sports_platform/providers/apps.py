"""
Providers Django app configuration.

Registers the ProviderRegistry singleton with all configured adapters
once Django has fully initialized (in ready()).
"""
import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ProvidersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sports_platform.providers"
    label = "providers"
    verbose_name = "Sports Data Providers"

    def ready(self):
        """Register all active providers into the singleton registry."""
        self._register_providers()

    @staticmethod
    def _register_providers():
        """
        Initialize and register provider adapters.
        Only registers a provider if its API key is configured.
        Fails silently (with a warning) so the app starts without any provider configured.
        """
        from django.conf import settings
        from sports_platform.providers.registry import get_registry
        from sports_platform.providers.adapters.api_football import ApiFootballAdapter

        registry = get_registry()

        # ApiFootball (football provider)
        api_football_key = getattr(settings, "API_FOOTBALL_KEY", None)
        if api_football_key:
            try:
                adapter = ApiFootballAdapter(api_key=api_football_key)
                registry.register_sports_provider(adapter, priority=10)
                logger.info("ApiFootballAdapter registered")
            except Exception as exc:
                logger.warning(
                    "Failed to register ApiFootballAdapter",
                    extra={"error": str(exc)},
                )
        else:
            logger.warning(
                "API_FOOTBALL_KEY not set — ApiFootballAdapter not registered. "
                "Set API_FOOTBALL_KEY in your .env to enable football data."
            )
