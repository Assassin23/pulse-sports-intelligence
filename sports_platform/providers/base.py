"""
Abstract base provider interface and Pydantic DTO models.

DTOs (ProviderMatch, ProviderScore, ProviderMatchEvent, ProviderOdds) use
Pydantic BaseModel for:
  - Automatic field validation on construction
  - Type coercion (e.g., provider returns "33" string → kept as validated str)
  - .model_dump() / .model_dump_json() for clean Kafka serialization (Milestone 3)
  - .model_validate(dict) for clean reconstruction from Kafka consumer messages
  - Self-documenting schema (fields, types, defaults all explicit)

The abstract interface classes (SportsDataProvider, OddsDataProvider) remain
standard ABC — Pydantic doesn't apply to interface contracts.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Internal Status Enum ─────────────────────────────────────────────────────

class MatchStatus(str, Enum):
    """
    Internal canonical match status values.
    Provider-specific strings are mapped to these before constructing DTOs.
    """
    SCHEDULED = "scheduled"
    LIVE = "live"
    HALF_TIME = "half_time"
    COMPLETED = "completed"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    INTERRUPTED = "interrupted"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


# ── Base DTO config ───────────────────────────────────────────────────────────

class _ProviderDTO(BaseModel):
    """
    Shared config for all provider DTOs.
    - frozen=True: immutable after construction — safe to pass across threads/queues
    - validate_assignment=False: no re-validation on attribute set (frozen prevents it anyway)
    - populate_by_name=True: allows both alias and field name construction
    """
    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        # Exclude 'raw' from equality checks — two ProviderMatch are equal if
        # domain fields match, even if raw payloads differ (e.g., enriched copy)
        # This is enforced via __eq__ override below where needed.
    )


# ── Provider DTOs ─────────────────────────────────────────────────────────────

class ProviderMatch(_ProviderDTO):
    """
    Normalized match data returned by a provider adapter.
    Provider-specific fields are mapped to internal names before construction.

    Serialization (for Kafka, Milestone 3):
        payload = match.model_dump(exclude={"raw"})
        json_bytes = match.model_dump_json(exclude={"raw"}).encode()

    Deserialization (Kafka consumer, Milestone 3):
        match = ProviderMatch.model_validate(json.loads(message.value))
    """

    provider_match_id: str = Field(description="Provider's unique match ID (string)")
    sport: str = Field(description="Internal sport slug: 'football', 'cricket', etc.")
    competition_name: str
    competition_provider_id: str
    home_team_name: str
    home_team_provider_id: str
    away_team_name: str
    away_team_provider_id: str
    scheduled_at: datetime = Field(description="Match kick-off time (timezone-aware UTC)")
    status: MatchStatus = Field(description="Internal normalized match status")
    venue: Optional[str] = None
    round: Optional[str] = None
    season: Optional[str] = None
    raw: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original provider payload for debugging/replay. Excluded from Kafka.",
        exclude=True,  # excluded by default in model_dump(); override with include={'raw'}
    )

    @field_validator("provider_match_id", "competition_provider_id",
                     "home_team_provider_id", "away_team_provider_id", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        """Provider IDs sometimes arrive as integers. Normalize to string."""
        return str(v)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        """Accept both enum values and raw strings; unknown → MatchStatus.UNKNOWN."""
        if isinstance(v, MatchStatus):
            return v
        try:
            return MatchStatus(v)
        except ValueError:
            return MatchStatus.UNKNOWN


class ProviderScore(_ProviderDTO):
    """
    Normalized current score snapshot for a live match.

    score_data is intentionally untyped (dict) because the schema is
    sport-specific:
      Football: {"home": 2, "away": 1, "halftime": {"home": 1, "away": 0}}
      Cricket:  {"runs": 145, "wickets": 4, "overs": "18.3", "target": 200}
    Sport-specific typed models will be introduced in Milestone 4.
    """

    provider_match_id: str
    sport: str
    score_data: Dict[str, Any] = Field(description="Sport-specific score payload")
    sequence_number: int = Field(
        description="Monotonically increasing sequence for idempotency checks"
    )
    source_timestamp: datetime = Field(description="Provider-side timestamp (UTC)")

    @field_validator("provider_match_id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: Any) -> str:
        return str(v)


class ProviderMatchEvent(_ProviderDTO):
    """
    A single normalized in-game event (goal, wicket, yellow card, etc.).

    event_sequence is used by consumers to deduplicate and order events.
    """

    provider_match_id: str
    sport: str
    event_type: str = Field(
        description="Internal event type: 'goal', 'wicket', 'red_card', 'substitution', etc."
    )
    event_sequence: int = Field(description="Monotonically increasing sequence within match")
    occurred_at: Optional[datetime] = None
    minute: Optional[int] = Field(default=None, description="Match minute (football: 0-90+)")
    over_ball: Optional[str] = Field(default=None, description="Cricket over.ball notation: '14.3'")
    player_provider_id: Optional[str] = None
    player_name: Optional[str] = None
    secondary_player_provider_id: Optional[str] = None
    secondary_player_name: Optional[str] = None
    team_provider_id: Optional[str] = None
    description: Optional[str] = None
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific extra metadata",
    )

    @field_validator("provider_match_id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: Any) -> str:
        return str(v)


class ProviderOdds(_ProviderDTO):
    """Normalized betting odds for a match market."""

    provider_match_id: str
    sport: str
    market_type: str = Field(
        description="Normalized market: 'match_winner', 'handicap', 'over_under'"
    )
    bookmaker: str
    outcomes: List[Dict[str, Any]] = Field(
        description='[{"outcome": "home_win", "value": 1.85}, ...]'
    )
    odds_timestamp: datetime


# ── Abstract Provider Interfaces ─────────────────────────────────────────────
# These remain standard ABC — Pydantic doesn't apply to interface contracts.

class SportsDataProvider(ABC):
    """
    Abstract base class all sports data provider adapters must implement.
    Core business logic calls the registry; never calls adapters directly.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique stable identifier: 'api_football', 'cricapi', etc."""
        ...

    @property
    @abstractmethod
    def supported_sports(self) -> List[str]:
        """Sport slugs this provider covers, e.g. ['football']."""
        ...

    @abstractmethod
    def fetch_upcoming_fixtures(
        self, sport: str, days_ahead: int = 3
    ) -> List[ProviderMatch]:
        """Fetch upcoming scheduled matches."""
        ...

    @abstractmethod
    def fetch_live_matches(self, sport: str) -> List[ProviderMatch]:
        """Fetch all currently live matches for a sport."""
        ...

    @abstractmethod
    def fetch_live_score(
        self, provider_match_id: str
    ) -> Optional[ProviderScore]:
        """Fetch current score for a specific live match."""
        ...

    @abstractmethod
    def fetch_match_events(
        self, provider_match_id: str, since_sequence: int = 0
    ) -> List[ProviderMatchEvent]:
        """Fetch in-match events, optionally only newer than since_sequence."""
        ...

    @abstractmethod
    def fetch_match_statistics(self, provider_match_id: str) -> dict:
        """Fetch match statistics snapshot (possession, shots, etc.)."""
        ...


class OddsDataProvider(ABC):
    """Separate interface for betting odds providers."""

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


# ── Typed Exceptions ─────────────────────────────────────────────────────────

class ProviderCircuitOpenError(Exception):
    """Raised when a circuit breaker is OPEN for a provider."""
    pass


class ProviderAPIError(Exception):
    """Raised for non-retryable provider API errors (4xx, 5xx)."""
    pass


class ProviderRateLimitError(Exception):
    """Raised when the provider returns HTTP 429."""
    pass
