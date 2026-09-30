"""
ApiFootball adapter (api-football.com via RapidAPI).

Implements SportsDataProvider for the 'football' sport.
All API responses are normalized into internal ProviderMatch / ProviderScore /
ProviderMatchEvent types before returning to caller.

API Docs: https://www.api-football.com/documentation-v3
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from sports_platform.providers.base import (
    MatchStatus,
    ProviderAPIError,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderRateLimitError,
    ProviderScore,
    SportsDataProvider,
)

logger = logging.getLogger(__name__)


class ApiFootballAdapter(SportsDataProvider):
    """
    Adapter for api-football.com (RapidAPI-based).

    Set the API key via the API_FOOTBALL_KEY environment variable.
    Registered in ProviderRegistry by ProvidersConfig.ready().
    """

    PROVIDER_NAME = "api_football"
    BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"

    # Map provider status codes → internal MatchStatus enum
    STATUS_MAP: dict = {
        "NS": MatchStatus.SCHEDULED,
        "TBD": MatchStatus.SCHEDULED,
        "1H": MatchStatus.LIVE,
        "2H": MatchStatus.LIVE,
        "ET": MatchStatus.LIVE,
        "P": MatchStatus.LIVE,
        "HT": MatchStatus.HALF_TIME,
        "FT": MatchStatus.COMPLETED,
        "AET": MatchStatus.COMPLETED,
        "PEN": MatchStatus.COMPLETED,
        "BT": MatchStatus.LIVE,
        "SUSP": MatchStatus.SUSPENDED,
        "INT": MatchStatus.INTERRUPTED,
        "PST": MatchStatus.POSTPONED,
        "CANC": MatchStatus.CANCELLED,
        "ABD": MatchStatus.ABANDONED,
        "AWD": MatchStatus.COMPLETED,
        "WO": MatchStatus.COMPLETED,
        "LIVE": MatchStatus.LIVE,
    }

    # Map provider event types → internal event types
    EVENT_TYPE_MAP: dict = {
        "Goal": "goal",
        "subst": "substitution",
        "Var": "var_decision",
        "Miss": "missed_chance",
    }

    CARD_TYPE_MAP: dict = {
        "Yellow Card": "yellow_card",
        "Red Card": "red_card",
        "Yellow Red Card": "second_yellow",
    }

    def __init__(self, api_key: str, timeout: float = 10.0):
        self._api_key = api_key
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def supported_sports(self) -> List[str]:
        return ["football"]

    # ── HTTP Client ───────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict) -> dict:
        """Execute a GET request, raising typed exceptions on failure."""
        headers = {"x-apisports-key": self._api_key}
        try:
            response = httpx.get(
                f"{self.BASE_URL}{path}",
                headers=headers,
                params=params,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderAPIError(
                f"[{self.PROVIDER_NAME}] Timeout on {path}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderAPIError(
                f"[{self.PROVIDER_NAME}] Request error on {path}: {exc}"
            ) from exc

        if response.status_code == 429:
            raise ProviderRateLimitError(
                f"[{self.PROVIDER_NAME}] Rate limited on {path}"
            )
        if response.status_code >= 500:
            raise ProviderAPIError(
                f"[{self.PROVIDER_NAME}] Server error {response.status_code} on {path}"
            )
        if response.status_code >= 400:
            raise ProviderAPIError(
                f"[{self.PROVIDER_NAME}] Client error {response.status_code} on {path}: {response.text}"
            )

        return response.json()

    # ── SportsDataProvider interface ─────────────────────────────────────────

    def fetch_upcoming_fixtures(
        self, sport: str, days_ahead: int = 3
    ) -> List[ProviderMatch]:
        data = self._get("/fixtures", params={"next": days_ahead * 10})
        fixtures = data.get("response", [])
        logger.info(
            "Fetched upcoming fixtures",
            extra={"provider": self.PROVIDER_NAME, "count": len(fixtures), "days_ahead": days_ahead},
        )
        return [self._normalize_fixture(f) for f in fixtures]

    def fetch_live_matches(self, sport: str) -> List[ProviderMatch]:
        data = self._get("/fixtures", params={"live": "all"})
        fixtures = data.get("response", [])
        logger.info(
            "Fetched live matches",
            extra={"provider": self.PROVIDER_NAME, "count": len(fixtures)},
        )
        return [self._normalize_fixture(f) for f in fixtures]

    def fetch_live_score(self, provider_match_id: str) -> Optional[ProviderScore]:
        data = self._get("/fixtures", params={"id": provider_match_id})
        items = data.get("response", [])
        if not items:
            return None
        f = items[0]
        return ProviderScore(
            provider_match_id=str(f["fixture"]["id"]),
            sport="football",
            score_data={
                "home": f["goals"].get("home"),
                "away": f["goals"].get("away"),
                "halftime": f["score"].get("halftime"),
                "fulltime": f["score"].get("fulltime"),
                "extratime": f["score"].get("extratime"),
                "penalty": f["score"].get("penalty"),
            },
            sequence_number=f["fixture"]["timestamp"],
            source_timestamp=datetime.fromtimestamp(
                f["fixture"]["timestamp"], tz=timezone.utc
            ),
        )

    def fetch_match_events(
        self, provider_match_id: str, since_sequence: int = 0
    ) -> List[ProviderMatchEvent]:
        data = self._get("/fixtures/events", params={"fixture": provider_match_id})
        events = data.get("response", [])
        normalized = []
        for i, ev in enumerate(events):
            event_type = ev.get("type", "")
            detail = ev.get("detail", "")

            if event_type == "Card":
                internal_type = self.CARD_TYPE_MAP.get(detail, "card")
            else:
                internal_type = self.EVENT_TYPE_MAP.get(event_type, event_type.lower())

            normalized.append(
                ProviderMatchEvent(
                    provider_match_id=provider_match_id,
                    sport="football",
                    event_type=internal_type,
                    event_sequence=i,
                    occurred_at=None,
                    minute=ev.get("time", {}).get("elapsed"),
                    player_name=ev.get("player", {}).get("name"),
                    secondary_player_name=ev.get("assist", {}).get("name"),
                    team_provider_id=str(ev.get("team", {}).get("id", "")),
                    description=detail,
                    extra={"comments": ev.get("comments")},
                )
            )
        # Filter events after since_sequence for incremental fetching
        return [e for e in normalized if e.event_sequence > since_sequence]

    def fetch_match_statistics(self, provider_match_id: str) -> dict:
        data = self._get("/fixtures/statistics", params={"fixture": provider_match_id})
        return data.get("response", {})

    # ── Normalization ────────────────────────────────────────────────────────

    def _normalize_fixture(self, raw: dict) -> ProviderMatch:
        fixture = raw["fixture"]
        league = raw.get("league", {})
        teams = raw.get("teams", {})
        return ProviderMatch(
            provider_match_id=str(fixture["id"]),
            sport="football",
            competition_name=league.get("name", ""),
            competition_provider_id=str(league.get("id", "")),
            home_team_name=teams.get("home", {}).get("name", ""),
            home_team_provider_id=str(teams.get("home", {}).get("id", "")),
            away_team_name=teams.get("away", {}).get("name", ""),
            away_team_provider_id=str(teams.get("away", {}).get("id", "")),
            scheduled_at=datetime.fromtimestamp(
                fixture["timestamp"], tz=timezone.utc
            ),
            status=self.STATUS_MAP.get(
                fixture.get("status", {}).get("short", ""), "unknown"
            ),
            venue=fixture.get("venue", {}).get("name"),
            round=league.get("round"),
            season=str(league.get("season", "")),
            raw=raw,
        )
