# 6. External Provider Architecture

## 6.1 Design Goals

- **Provider independence:** Core business logic never imports or calls a provider SDK directly.
- **Pluggable adapters:** Adding a new provider requires only implementing the `SportsDataProvider` interface.
- **Failover support:** Multiple providers can serve the same data; if one fails, the system falls back automatically.
- **No coupling to polling cadence:** Each provider has its own polling schedule configured externally.
- **Provider data is normalized** before entering Kafka. Internal events use internal domain models only.

---

## 6.2 Provider Interface Contract

```python
# sports_platform/providers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class ProviderMatch:
    """Raw match data from provider, pre-normalization."""
    provider_match_id: str
    sport: str
    competition_name: str
    competition_provider_id: str
    home_team_name: str
    home_team_provider_id: str
    away_team_name: str
    away_team_provider_id: str
    scheduled_at: datetime
    status: str  # provider-specific status string, normalized by adapter
    venue: Optional[str] = None
    round: Optional[str] = None
    raw: dict = None  # original raw payload for debugging


@dataclass
class ProviderScore:
    provider_match_id: str
    sport: str
    score_data: dict      # sport-specific, normalized by adapter
    sequence_number: int
    source_timestamp: datetime


@dataclass
class ProviderMatchEvent:
    provider_match_id: str
    sport: str
    event_type: str       # normalized event type: 'goal', 'wicket', 'red_card', etc.
    event_sequence: int
    occurred_at: Optional[datetime]
    minute: Optional[int]
    over_ball: Optional[str]
    player_provider_id: Optional[str]
    player_name: Optional[str]
    secondary_player_provider_id: Optional[str]
    secondary_player_name: Optional[str]
    team_provider_id: Optional[str]
    description: Optional[str]
    extra: dict = None


@dataclass
class ProviderOdds:
    provider_match_id: str
    sport: str
    market_type: str      # normalized: 'match_winner', 'handicap', 'over_under'
    bookmaker: str
    outcomes: List[dict]  # [{"outcome": "home_win", "value": 1.85}, ...]
    odds_timestamp: datetime


class SportsDataProvider(ABC):
    """
    Abstract base class for all sports data providers.
    Implementors: ProviderAAdapter, ProviderBAdapter, etc.
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this provider: 'provider_a', 'api_football', etc."""
        ...

    @property
    @abstractmethod
    def supported_sports(self) -> List[str]:
        """List of sport slugs this provider supports."""
        ...

    @abstractmethod
    def fetch_upcoming_fixtures(
        self, sport: str, days_ahead: int = 3
    ) -> List[ProviderMatch]:
        """Fetch upcoming scheduled matches."""
        ...

    @abstractmethod
    def fetch_live_matches(self, sport: str) -> List[ProviderMatch]:
        """Fetch all currently live matches."""
        ...

    @abstractmethod
    def fetch_live_score(self, provider_match_id: str) -> Optional[ProviderScore]:
        """Fetch current score for a specific live match."""
        ...

    @abstractmethod
    def fetch_match_events(
        self, provider_match_id: str, since_sequence: int = 0
    ) -> List[ProviderMatchEvent]:
        """Fetch match events, optionally since a sequence number."""
        ...

    @abstractmethod
    def fetch_match_statistics(self, provider_match_id: str) -> dict:
        """Fetch match statistics snapshot."""
        ...


class OddsDataProvider(ABC):
    """Separate interface for odds providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def fetch_match_odds(
        self, provider_match_id: str, markets: List[str]
    ) -> List[ProviderOdds]:
        ...

    @abstractmethod
    def fetch_odds_for_sport(
        self, sport: str, match_ids: List[str]
    ) -> List[ProviderOdds]:
        ...
```

---

## 6.3 Concrete Adapter Example

```python
# sports_platform/providers/adapters/api_football.py

import httpx
from datetime import datetime, timezone
from typing import List, Optional

from sports_platform.providers.base import (
    SportsDataProvider, ProviderMatch, ProviderScore, ProviderMatchEvent
)


class ApiFootballAdapter(SportsDataProvider):
    """
    Adapter for api-football.com (RapidAPI).
    Translates provider-specific API responses to internal domain types.
    """

    PROVIDER_NAME = "api_football"
    BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"

    # Map provider status strings to internal status
    STATUS_MAP = {
        "NS": "scheduled",
        "1H": "live",
        "2H": "live",
        "HT": "half_time",
        "FT": "completed",
        "AET": "completed",
        "PEN": "completed",
        "PST": "postponed",
        "CANC": "cancelled",
        "ABD": "abandoned",
    }

    EVENT_TYPE_MAP = {
        "Goal": "goal",
        "subst": "substitution",
        "Card": None,  # check sub-type
        "Var": "var_decision",
    }

    def __init__(self, api_key: str, timeout: float = 10.0):
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"x-apisports-key": self._api_key},
            timeout=timeout,
        )

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def supported_sports(self) -> List[str]:
        return ["football"]

    def fetch_upcoming_fixtures(self, sport: str, days_ahead: int = 3) -> List[ProviderMatch]:
        response = self._client.get("/fixtures", params={"next": days_ahead * 10})
        response.raise_for_status()
        data = response.json()
        return [self._normalize_fixture(f) for f in data.get("response", [])]

    def fetch_live_matches(self, sport: str) -> List[ProviderMatch]:
        response = self._client.get("/fixtures", params={"live": "all"})
        response.raise_for_status()
        data = response.json()
        return [self._normalize_fixture(f) for f in data.get("response", [])]

    def fetch_live_score(self, provider_match_id: str) -> Optional[ProviderScore]:
        response = self._client.get("/fixtures", params={"id": provider_match_id})
        response.raise_for_status()
        data = response.json()
        if not data.get("response"):
            return None
        f = data["response"][0]
        return ProviderScore(
            provider_match_id=str(f["fixture"]["id"]),
            sport="football",
            score_data={
                "home": f["goals"]["home"],
                "away": f["goals"]["away"],
                "halftime": f["score"]["halftime"],
                "fulltime": f["score"]["fulltime"],
            },
            sequence_number=f["fixture"]["timestamp"],
            source_timestamp=datetime.fromtimestamp(
                f["fixture"]["timestamp"], tz=timezone.utc
            ),
        )

    def _normalize_fixture(self, raw: dict) -> ProviderMatch:
        fixture = raw["fixture"]
        return ProviderMatch(
            provider_match_id=str(fixture["id"]),
            sport="football",
            competition_name=raw["league"]["name"],
            competition_provider_id=str(raw["league"]["id"]),
            home_team_name=raw["teams"]["home"]["name"],
            home_team_provider_id=str(raw["teams"]["home"]["id"]),
            away_team_name=raw["teams"]["away"]["name"],
            away_team_provider_id=str(raw["teams"]["away"]["id"]),
            scheduled_at=datetime.fromtimestamp(
                fixture["timestamp"], tz=timezone.utc
            ),
            status=self.STATUS_MAP.get(fixture["status"]["short"], "unknown"),
            venue=fixture.get("venue", {}).get("name"),
            raw=raw,
        )

    def fetch_match_events(self, provider_match_id: str, since_sequence: int = 0):
        # Implementation follows same pattern
        ...

    def fetch_match_statistics(self, provider_match_id: str) -> dict:
        # Implementation follows same pattern
        ...
```

---

## 6.4 Provider Registry

```python
# sports_platform/providers/registry.py

from typing import Dict, List
from sports_platform.providers.base import SportsDataProvider, OddsDataProvider


class ProviderRegistry:
    """
    Central registry of all data providers.
    Core logic calls registry; never calls adapters directly.
    """

    def __init__(self):
        self._sports_providers: Dict[str, SportsDataProvider] = {}
        self._odds_providers: Dict[str, OddsDataProvider] = {}
        self._sport_to_providers: Dict[str, List[str]] = {}

    def register_sports_provider(self, provider: SportsDataProvider, priority: int = 0):
        name = provider.provider_name
        self._sports_providers[name] = provider
        for sport in provider.supported_sports:
            if sport not in self._sport_to_providers:
                self._sport_to_providers[sport] = []
            self._sport_to_providers[sport].append((priority, name))
            self._sport_to_providers[sport].sort(reverse=True)

    def get_providers_for_sport(self, sport: str) -> List[SportsDataProvider]:
        """Returns providers for a sport, ordered by priority (highest first)."""
        entries = self._sport_to_providers.get(sport, [])
        return [self._sports_providers[name] for _, name in entries]

    def get_primary_provider(self, sport: str) -> SportsDataProvider:
        providers = self.get_providers_for_sport(sport)
        if not providers:
            raise ValueError(f"No provider registered for sport: {sport}")
        return providers[0]
```

---

## 6.5 Ingestion Worker

```python
# sports_platform/ingestion/workers/sports_ingestion_worker.py

import logging
from datetime import datetime
from sports_platform.providers.registry import ProviderRegistry
from sports_platform.kafka.producer import KafkaEventProducer
from sports_platform.providers.base import SportsDataProvider

logger = logging.getLogger(__name__)


class SportsIngestionWorker:
    """
    Polls a provider for live/upcoming data and publishes raw-normalized
    events to Kafka. Does NOT write to PostgreSQL or Redis.
    """

    def __init__(self, provider: SportsDataProvider, producer: KafkaEventProducer):
        self._provider = provider
        self._producer = producer

    def ingest_live_matches(self, sport: str):
        try:
            matches = self._provider.fetch_live_matches(sport)
        except Exception as e:
            logger.error(
                "Provider fetch failed",
                extra={"provider": self._provider.provider_name, "sport": sport, "error": str(e)},
            )
            return  # Fail silently; next poll cycle will retry

        for match in matches:
            self._producer.publish_score_update(match)
            # Also triggers match.discovered if new

    def ingest_upcoming_fixtures(self, sport: str, days_ahead: int = 3):
        try:
            fixtures = self._provider.fetch_upcoming_fixtures(sport, days_ahead)
        except Exception as e:
            logger.error("Fixture fetch failed", extra={"error": str(e)})
            return

        for fixture in fixtures:
            self._producer.publish_match_discovered(fixture)
```

---

## 6.6 Failover Strategy

```
For each sport, register providers by priority:
  Priority 1 (primary):   Provider A
  Priority 2 (fallback):  Provider B

Ingestion worker:
  1. Try primary provider
  2. If HTTP error / timeout after 3 retries → log warning, try fallback
  3. If all providers fail → log error, metric increment, skip cycle
  4. Circuit breaker: if provider fails >5 consecutive times → mark OPEN for 5 min
  5. Serve stale data from Redis (last-known-good state) to clients
```

---

## 6.7 Adding a New Provider Checklist

1. Implement `SportsDataProvider` or `OddsDataProvider` in `providers/adapters/`.
2. Map all provider-specific status strings and event types to internal enums.
3. Add provider configuration to Django settings / env vars.
4. Register in the `ProviderRegistry` in `settings.py` or an `AppConfig.ready()`.
5. Add provider-specific integration tests with VCR cassettes (recorded HTTP responses).
6. Configure Celery Beat schedule for the new provider's polling tasks.
