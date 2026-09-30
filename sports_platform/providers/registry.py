"""
Provider Registry: central catalogue of registered SportsDataProviders.

Domain services call the registry to resolve the best provider for a sport.
Providers are registered with priorities; the highest-priority provider
is attempted first. On failure, the circuit breaker handles failover.
"""
import logging
from typing import Dict, List, Optional

from sports_platform.providers.base import (
    OddsDataProvider,
    ProviderCircuitOpenError,
    SportsDataProvider,
)
from sports_platform.providers.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Central registry of all sports/odds data providers.

    Usage:
        registry = ProviderRegistry()
        registry.register_sports_provider(ApiFootballAdapter(...), priority=10)
        provider = registry.get_primary_provider("football")
    """

    def __init__(self):
        self._sports_providers: Dict[str, SportsDataProvider] = {}
        self._odds_providers: Dict[str, OddsDataProvider] = {}
        # {sport_slug: [(priority, provider_name), ...]} — sorted descending
        self._sport_to_providers: Dict[str, List] = {}
        # One circuit breaker per provider
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    # ── Registration ─────────────────────────────────────────────────────────

    def register_sports_provider(
        self,
        provider: SportsDataProvider,
        priority: int = 0,
        failure_threshold: int = 5,
    ) -> None:
        """Register a sports provider with an optional priority (higher = preferred)."""
        name = provider.provider_name
        self._sports_providers[name] = provider
        self._circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
        )
        for sport in provider.supported_sports:
            if sport not in self._sport_to_providers:
                self._sport_to_providers[sport] = []
            # Avoid duplicate registration
            if not any(n == name for _, n in self._sport_to_providers[sport]):
                self._sport_to_providers[sport].append((priority, name))
                self._sport_to_providers[sport].sort(key=lambda x: x[0], reverse=True)
        logger.info(
            "Provider registered",
            extra={"provider": name, "sports": provider.supported_sports, "priority": priority},
        )

    def register_odds_provider(self, provider: OddsDataProvider) -> None:
        self._odds_providers[provider.provider_name] = provider

    # ── Lookups ──────────────────────────────────────────────────────────────

    def get_providers_for_sport(self, sport: str) -> List[SportsDataProvider]:
        """Return providers for a sport ordered by priority (highest first)."""
        entries = self._sport_to_providers.get(sport, [])
        return [
            self._sports_providers[name]
            for _, name in entries
            if name in self._sports_providers
        ]

    def get_primary_provider(self, sport: str) -> SportsDataProvider:
        """Return the highest-priority available (non-open-circuit) provider."""
        providers = self.get_providers_for_sport(sport)
        if not providers:
            raise ValueError(f"No provider registered for sport: '{sport}'")
        # Prefer providers whose circuit is not OPEN
        for provider in providers:
            cb = self._circuit_breakers.get(provider.provider_name)
            from sports_platform.providers.circuit_breaker import CircuitState
            if cb is None or cb.state != CircuitState.OPEN:
                return provider
        # All circuits open — return primary anyway (it will raise ProviderCircuitOpenError)
        return providers[0]

    def get_circuit_breaker(self, provider_name: str) -> Optional[CircuitBreaker]:
        return self._circuit_breakers.get(provider_name)

    def call_with_circuit_breaker(self, provider_name: str, func, *args, **kwargs):
        """Execute a provider call wrapped in its circuit breaker."""
        cb = self._circuit_breakers.get(provider_name)
        if cb is None:
            return func(*args, **kwargs)
        return cb.call(func, *args, **kwargs)

    def list_providers(self) -> Dict[str, List[str]]:
        """Return a summary dict: {provider_name: [sport_slugs]}"""
        return {
            name: provider.supported_sports
            for name, provider in self._sports_providers.items()
        }


# ── Singleton registry instance ───────────────────────────────────────────────
# Initialized in apps.py ready() so providers are registered after Django setup.
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
