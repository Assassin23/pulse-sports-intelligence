"""
Abstract base provider interface and shared domain dataclasses.

All sports data providers must implement SportsDataProvider.
This ensures the core business logic is fully decoupled from
any specific provider SDK or API shape.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ProviderMatch:
    """
    Normalized match data returned by a provider adapter.
    Provider-specific data is pre-normalized before entering the system.
    """

    provider_match_id: str
    sport: str  # slug: 'cricket', 'football', etc.
    competition_name: str
    competition_provider_id: str
    home_team_name: str
    home_team_provider_id: str
    away_team_name: str
    away_team_provider_id: str
    scheduled_at: datetime
    status: str  # internal status: scheduled, live, completed, postponed, cancelled
    venue: Optional[str] = None
    round: Optional[str] = None
    season: Optional[str] = None
    raw: Optional[dict] = None  # original payload for debugging/replay


@dataclass
class ProviderScore:
    """Normalized current score snapshot for a live match."""

    provider_match_id: str
    sport: str
    score_data: dict  # sport-specific: {"home": 2, "away": 1} or {"runs": 145, "wickets": 4}
    sequence_number: int  # monotonically increasing; used for idempotency
    source_timestamp: datetime


@dataclass
class ProviderMatchEvent:
    """A normalized in-game event (goal, wicket, red card, etc.)."""

    provider_match_id: str
    sport: str
    event_type: str  # internal normalized type: 'goal', 'wicket', 'red_card', 'substitution'
    event_sequence: int
    occurred_at: Optional[datetime]
    minute: Optional[int] = None
    over_ball: Optional[str] = None  # Cricket: "14.3"
    player_provider_id: Optional[str] = None
    player_name: Optional[str] = None
    secondary_player_provider_id: Optional[str] = None
    secondary_player_name: Optional[str] = None
    team_provider_id: Optional[str] = None
    description: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class ProviderOdds:
    """Normalized betting odds for a match market."""

    provider_match_id: str
    sport: str
    market_type: str  # 'match_winner', 'handicap', 'over_under'
    bookmaker: str
    outcomes: List[dict]  # [{"outcome": "home_win", "value": 1.85}, ...]
    odds_timestamp: datetime


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


class ProviderCircuitOpenError(Exception):
    """Raised when a circuit breaker is OPEN for a provider."""

    pass


class ProviderAPIError(Exception):
    """Raised for non-retryable provider API errors."""

    pass


class ProviderRateLimitError(Exception):
    """Raised when the provider returns HTTP 429."""

    pass
