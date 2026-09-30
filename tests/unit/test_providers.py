"""
Unit tests for:
- ApiFootballAdapter (VCR cassette-driven, no real HTTP calls)
- CircuitBreaker state transitions
- ProviderRegistry priority resolution
- EntityMappingService dedup logic
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sports_platform.providers.adapters.api_football import ApiFootballAdapter
from sports_platform.providers.base import ProviderCircuitOpenError
from sports_platform.providers.circuit_breaker import CircuitBreaker, CircuitState
from sports_platform.providers.registry import ProviderRegistry

# ── Cassette helpers ─────────────────────────────────────────────────────────

CASSETTE_DIR = Path(__file__).parent.parent / "cassettes"


def _load_cassette(name: str) -> dict:
    return json.loads((CASSETTE_DIR / f"{name}.json").read_text())


# ── ApiFootballAdapter Tests ─────────────────────────────────────────────────

class TestApiFootballAdapterNormalization:
    """Test normalization logic using cassette payloads (no live HTTP)."""

    def _make_adapter(self):
        return ApiFootballAdapter(api_key="test-key-does-not-matter")

    def test_provider_name(self):
        adapter = self._make_adapter()
        assert adapter.provider_name == "api_football"

    def test_supported_sports(self):
        adapter = self._make_adapter()
        assert "football" in adapter.supported_sports

    def test_status_map_covers_common_codes(self):
        adapter = self._make_adapter()
        assert adapter.STATUS_MAP["NS"] == "scheduled"
        assert adapter.STATUS_MAP["1H"] == "live"
        assert adapter.STATUS_MAP["2H"] == "live"
        assert adapter.STATUS_MAP["HT"] == "half_time"
        assert adapter.STATUS_MAP["FT"] == "completed"
        assert adapter.STATUS_MAP["PST"] == "postponed"
        assert adapter.STATUS_MAP["CANC"] == "cancelled"

    def test_normalize_fixture_from_cassette(self):
        adapter = self._make_adapter()
        cassette = _load_cassette("api_football_upcoming_fixtures")
        raw_fixture = json.loads(
            cassette["interactions"][0]["response"]["body"]["string"]
        )["response"][0]

        result = adapter._normalize_fixture(raw_fixture)

        assert result.provider_match_id == "1208082"
        assert result.sport == "football"
        assert result.competition_name == "Premier League"
        assert result.competition_provider_id == "39"
        assert result.home_team_name == "Manchester United"
        assert result.home_team_provider_id == "33"
        assert result.away_team_name == "Newcastle"
        assert result.away_team_provider_id == "34"
        assert result.status == "scheduled"
        assert isinstance(result.scheduled_at, datetime)

    def test_normalize_multiple_fixtures(self):
        adapter = self._make_adapter()
        cassette = _load_cassette("api_football_upcoming_fixtures")
        raw_list = json.loads(
            cassette["interactions"][0]["response"]["body"]["string"]
        )["response"]

        results = [adapter._normalize_fixture(r) for r in raw_list]
        assert len(results) == 2
        assert results[0].provider_match_id == "1208082"
        assert results[1].provider_match_id == "1208083"
        # Second fixture: Liverpool vs Chelsea
        assert results[1].home_team_name == "Liverpool"
        assert results[1].away_team_name == "Chelsea"

    def test_fetch_upcoming_fixtures_uses_cassette(self):
        """Test the adapter via mocked HTTP using cassette body."""
        adapter = self._make_adapter()
        cassette = _load_cassette("api_football_upcoming_fixtures")
        cassette_body = cassette["interactions"][0]["response"]["body"]["string"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = json.loads(cassette_body)

        with patch("httpx.get", return_value=mock_response):
            fixtures = adapter.fetch_upcoming_fixtures("football", days_ahead=3)

        assert len(fixtures) == 2
        assert fixtures[0].status == "scheduled"
        assert fixtures[0].competition_name == "Premier League"

    def test_normalize_events_from_cassette(self):
        adapter = self._make_adapter()
        cassette = _load_cassette("api_football_match_events")
        cassette_body = cassette["interactions"][0]["response"]["body"]["string"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = json.loads(cassette_body)

        with patch("httpx.get", return_value=mock_response):
            events = adapter.fetch_match_events("1208082")

        assert len(events) == 3
        assert events[0].event_type == "goal"
        assert events[0].player_name == "Marcus Rashford"
        assert events[0].minute == 23
        assert events[2].event_type == "yellow_card"
        assert events[2].player_name == "Kobbie Mainoo"

    def test_event_type_map_card_detail(self):
        adapter = self._make_adapter()
        assert adapter.CARD_TYPE_MAP["Yellow Card"] == "yellow_card"
        assert adapter.CARD_TYPE_MAP["Red Card"] == "red_card"
        assert adapter.CARD_TYPE_MAP["Yellow Red Card"] == "second_yellow"

    def test_rate_limit_raises_typed_error(self):
        from sports_platform.providers.base import ProviderRateLimitError
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.status_code = 429
        with patch("httpx.get", return_value=mock_response):
            with pytest.raises(ProviderRateLimitError):
                adapter.fetch_upcoming_fixtures("football")

    def test_server_error_raises_typed_error(self):
        from sports_platform.providers.base import ProviderAPIError
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.status_code = 503
        with patch("httpx.get", return_value=mock_response):
            with pytest.raises(ProviderAPIError):
                adapter.fetch_live_matches("football")


# ── CircuitBreaker Tests ─────────────────────────────────────────────────────

class TestCircuitBreaker:
    def _make_cb(self, threshold=3) -> CircuitBreaker:
        return CircuitBreaker(name="test_provider", failure_threshold=threshold)

    def test_starts_closed(self):
        cb = self._make_cb()
        assert cb.state == CircuitState.CLOSED

    def test_success_keeps_closed(self):
        cb = self._make_cb()
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        cb = self._make_cb(threshold=3)

        def failing():
            raise RuntimeError("provider down")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(failing)

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_open_circuit_raises_immediately(self):
        cb = self._make_cb(threshold=1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitState.OPEN

        with pytest.raises(ProviderCircuitOpenError):
            cb.call(lambda: 42)

    def test_success_resets_failure_count(self):
        cb = self._make_cb(threshold=5)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.failure_count == 3

        cb.call(lambda: "ok")
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_half_open_allows_probe(self):
        cb = self._make_cb(threshold=1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitState.OPEN

        # Manually backdate last failure to simulate recovery window elapsed
        cb._last_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_reset_returns_to_closed(self):
        cb = self._make_cb(threshold=1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


# ── ProviderRegistry Tests ───────────────────────────────────────────────────

class TestProviderRegistry:
    def _make_provider(self, name: str, sports: list):
        p = MagicMock()
        p.provider_name = name
        p.supported_sports = sports
        return p

    def test_register_and_retrieve(self):
        registry = ProviderRegistry()
        p = self._make_provider("provider_a", ["football"])
        registry.register_sports_provider(p, priority=10)

        providers = registry.get_providers_for_sport("football")
        assert len(providers) == 1
        assert providers[0].provider_name == "provider_a"

    def test_priority_ordering(self):
        registry = ProviderRegistry()
        p1 = self._make_provider("low_priority", ["football"])
        p2 = self._make_provider("high_priority", ["football"])
        registry.register_sports_provider(p1, priority=5)
        registry.register_sports_provider(p2, priority=10)

        providers = registry.get_providers_for_sport("football")
        assert providers[0].provider_name == "high_priority"
        assert providers[1].provider_name == "low_priority"

    def test_get_primary_provider(self):
        registry = ProviderRegistry()
        p = self._make_provider("provider_a", ["cricket"])
        registry.register_sports_provider(p, priority=10)

        primary = registry.get_primary_provider("cricket")
        assert primary.provider_name == "provider_a"

    def test_no_provider_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="No provider"):
            registry.get_primary_provider("curling")

    def test_open_circuit_skipped_for_primary(self):
        registry = ProviderRegistry()
        p1 = self._make_provider("primary", ["football"])
        p2 = self._make_provider("fallback", ["football"])
        registry.register_sports_provider(p1, priority=10)
        registry.register_sports_provider(p2, priority=5)

        # Force primary CB open
        cb = registry.get_circuit_breaker("primary")
        cb._state = CircuitState.OPEN
        cb._last_failure_at = datetime.now(tz=timezone.utc)

        primary = registry.get_primary_provider("football")
        assert primary.provider_name == "fallback"


# ── EntityMappingService Tests ───────────────────────────────────────────────

@pytest.mark.django_db
class TestEntityMappingService:
    def test_register_and_resolve(self):
        from sports_platform.providers.mapping_service import EntityMappingService
        internal_id = uuid.uuid4()
        EntityMappingService.register("api_football", "team", "33", internal_id)
        resolved = EntityMappingService.resolve("api_football", "team", "33")
        assert resolved == internal_id

    def test_resolve_unknown_returns_none(self):
        from sports_platform.providers.mapping_service import EntityMappingService
        result = EntityMappingService.resolve("api_football", "team", "999999")
        assert result is None

    def test_register_idempotent(self):
        from sports_platform.providers.mapping_service import EntityMappingService
        from sports_platform.sports.models import ProviderEntityMapping
        internal_id = uuid.uuid4()
        EntityMappingService.register("api_football", "team", "77", internal_id)
        EntityMappingService.register("api_football", "team", "77", internal_id)
        count = ProviderEntityMapping.objects.filter(
            provider_name="api_football", provider_entity_id="77"
        ).count()
        assert count == 1

    def test_upsert_team_creates_and_maps(self):
        from tests.factories import SportFactory
        from sports_platform.providers.mapping_service import EntityMappingService
        sport = SportFactory(slug="football", name="Football")
        team = EntityMappingService.upsert_team(
            provider_name="api_football",
            provider_team_id="33",
            sport=sport,
            team_name="Manchester United",
        )
        assert team.name == "Manchester United"
        resolved = EntityMappingService.resolve("api_football", "team", "33")
        assert resolved == team.id

    def test_upsert_team_idempotent(self):
        from tests.factories import SportFactory
        from sports_platform.providers.mapping_service import EntityMappingService
        from sports_platform.sports.models import Team
        sport = SportFactory(slug="football2", name="Football2")
        EntityMappingService.upsert_team("api_football", "88", sport, "Arsenal")
        EntityMappingService.upsert_team("api_football", "88", sport, "Arsenal")
        assert Team.objects.filter(name="Arsenal").count() == 1
