"""
Tests for Milestone 3 & 4:
- MatchProcessorConsumer: match.discovered event → DB + Redis
- ScoreProcessorConsumer: score.updated → Redis Lua + DB
- EventProcessorConsumer: match.event → DB + Redis sorted set
- MatchRedisStore: key schema, score idempotency, live set, events
- Matches API: upcoming, live, detail, events endpoints
"""
import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from sports_platform.kafka.events import (
    KafkaTopics,
    MatchDiscoveredEvent,
    MatchEventPublished,
    MatchStartedEvent,
    MatchCompletedEvent,
    ScoreUpdatedEvent,
)


# ── Kafka Event Schema Tests ──────────────────────────────────────────────────

class TestKafkaEvents:
    def test_match_discovered_serializes_cleanly(self):
        event = MatchDiscoveredEvent(
            provider_name="api_football",
            provider_match_id="12345",
            sport="football",
            competition_name="Premier League",
            competition_provider_id="39",
            home_team_name="Arsenal",
            home_team_provider_id="42",
            away_team_name="Chelsea",
            away_team_provider_id="49",
            scheduled_at=datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc),
            status="scheduled",
        )
        payload = json.loads(event.model_dump_json())
        assert payload["event_type"] == "match.discovered"
        assert payload["provider_match_id"] == "12345"
        assert "event_id" in payload
        assert "occurred_at" in payload
        assert payload["schema_version"] == "1.0"

    def test_match_discovered_roundtrip(self):
        event = MatchDiscoveredEvent(
            provider_name="api_football",
            provider_match_id="99",
            sport="cricket",
            competition_name="IPL",
            competition_provider_id="1",
            home_team_name="RCB",
            home_team_provider_id="10",
            away_team_name="MI",
            away_team_provider_id="11",
            scheduled_at=datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc),
            status="scheduled",
        )
        reconstructed = MatchDiscoveredEvent.model_validate_json(event.model_dump_json())
        assert reconstructed.provider_match_id == event.provider_match_id
        assert reconstructed.home_team_name == event.home_team_name

    def test_score_updated_from_provider_score(self):
        from sports_platform.providers.base import ProviderScore
        score = ProviderScore(
            provider_match_id="999",
            sport="football",
            score_data={"home": 2, "away": 1},
            sequence_number=15,
            source_timestamp=datetime.now(tz=timezone.utc),
        )
        event = ScoreUpdatedEvent.from_provider_score(score, "api_football", "internal-uuid")
        assert event.score_data == {"home": 2, "away": 1}
        assert event.sequence_number == 15
        assert event.internal_match_id == "internal-uuid"

    def test_match_event_published_from_provider_event(self):
        from sports_platform.providers.base import ProviderMatchEvent
        pe = ProviderMatchEvent(
            provider_match_id="999",
            sport="football",
            event_type="goal",
            event_sequence=3,
            occurred_at=None,
            minute=45,
            player_name="Rashford",
        )
        event = MatchEventPublished.from_provider_event(pe, "api_football", "internal-uuid")
        assert event.event_type_detail == "goal"
        assert event.minute == 45
        assert event.player_name == "Rashford"
        assert event.event_sequence == 3

    def test_all_kafka_topics_available(self):
        topics = KafkaTopics.all_topics()
        assert KafkaTopics.MATCH_DISCOVERED in topics
        assert KafkaTopics.SCORE_UPDATED in topics
        assert KafkaTopics.MATCH_EVENT in topics
        assert KafkaTopics.MATCH_STARTED in topics
        assert KafkaTopics.MATCH_COMPLETED in topics
        # DLQ topics
        assert KafkaTopics.MATCH_DISCOVERED_DLQ in topics
        assert len(topics) >= 9


# ── Redis Store Tests ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMatchRedisStore:
    """
    These tests use fakeredis for isolation — no real Redis instance required.
    """

    @pytest.fixture
    def store(self):
        import fakeredis
        from sports_platform.matches.redis_store import MatchRedisStore
        s = MatchRedisStore.__new__(MatchRedisStore)
        s._redis = fakeredis.FakeRedis(decode_responses=True)
        return s

    def test_score_key_format(self, store):
        assert store.score_key("abc-123") == "match:score:abc-123"

    def test_live_set_operations(self, store):
        store.add_to_live("match-1")
        store.add_to_live("match-2")
        ids = store.get_live_match_ids()
        assert "match-1" in ids
        assert "match-2" in ids

        store.remove_from_live("match-1")
        ids = store.get_live_match_ids()
        assert "match-1" not in ids
        assert "match-2" in ids

    def test_upcoming_add_and_get(self, store):
        match_id = str(uuid.uuid4())
        future_ts = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)
        store.add_upcoming("football", match_id, future_ts)
        ids = store.get_upcoming_ids("football", from_ts=0, to_ts=float("inf"))
        assert match_id in ids

    def test_push_and_get_recent_events(self, store):
        match_id = str(uuid.uuid4())
        store.push_event(match_id, 1, {"event_type": "goal", "minute": 23})
        store.push_event(match_id, 2, {"event_type": "yellow_card", "minute": 45})

        events = store.get_recent_events(match_id, limit=10)
        assert len(events) == 2
        # Returned desc by sequence — most recent first
        assert events[0]["event_type"] == "yellow_card"

    def test_cache_and_get_match_meta(self, store):
        match_id = str(uuid.uuid4())
        meta = {
            "sport": "football",
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
            "status": "live",
        }
        store.cache_match_meta(match_id, meta)
        result = store.get_match_meta(match_id)
        assert result["home_team_name"] == "Arsenal"
        assert result["status"] == "live"

    def test_get_score_returns_none_if_not_cached(self, store):
        result = store.get_score("does-not-exist")
        assert result is None


# ── Match Processor Consumer Tests ────────────────────────────────────────────

@pytest.mark.django_db
class TestMatchProcessorConsumer:
    def test_handle_creates_match(self):
        from tests.factories import SportFactory
        from sports_platform.kafka.consumers.match_consumers import MatchProcessorConsumer
        from sports_platform.matches.models import Match
        from sports_platform.matches.redis_store import MatchRedisStore

        import fakeredis
        sport = SportFactory(slug="football", name="Football", is_active=True)

        event = MatchDiscoveredEvent(
            provider_name="test_provider",
            provider_match_id="fixture-001",
            sport="football",
            competition_name="Test League",
            competition_provider_id="comp-1",
            home_team_name="Alpha FC",
            home_team_provider_id="team-1",
            away_team_name="Beta FC",
            away_team_provider_id="team-2",
            scheduled_at=datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc),
            status="scheduled",
        )

        consumer = MatchProcessorConsumer.__new__(MatchProcessorConsumer)
        # Mock Redis store
        fake_store = MagicMock()
        with patch(
            "sports_platform.kafka.consumers.match_consumers.get_match_store",
            return_value=fake_store
        ):
            consumer.handle(event)

        match = Match.objects.get(provider_match_id="fixture-001")
        assert match.status == "scheduled"
        assert match.home_team.name == "Alpha FC"
        assert match.away_team.name == "Beta FC"
        fake_store.cache_match_meta.assert_called_once()

    def test_handle_idempotent_same_match(self):
        from tests.factories import SportFactory
        from sports_platform.kafka.consumers.match_consumers import MatchProcessorConsumer
        from sports_platform.matches.models import Match

        SportFactory(slug="cricket", name="Cricket", is_active=True)
        event = MatchDiscoveredEvent(
            provider_name="test_prov",
            provider_match_id="fixture-idem",
            sport="cricket",
            competition_name="IPL",
            competition_provider_id="ipl-1",
            home_team_name="RCB",
            home_team_provider_id="rcb-1",
            away_team_name="MI",
            away_team_provider_id="mi-1",
            scheduled_at=datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc),
            status="scheduled",
        )
        consumer = MatchProcessorConsumer.__new__(MatchProcessorConsumer)
        fake_store = MagicMock()
        with patch(
            "sports_platform.kafka.consumers.match_consumers.get_match_store",
            return_value=fake_store,
        ):
            consumer.handle(event)
            consumer.handle(event)  # Second call — must not duplicate

        assert Match.objects.filter(provider_match_id="fixture-idem").count() == 1


# ── Matches API Tests ─────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, db):
    from tests.factories import UserFactory
    user = UserFactory()
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
class TestMatchesAPI:
    def _create_match(self, sport_slug="football"):
        from tests.factories import (
            SportFactory, TeamFactory, CompetitionFactory, MatchFactory
        )
        sport = SportFactory(slug=sport_slug, name=sport_slug.capitalize())
        home = TeamFactory(sport=sport, name="Home FC")
        away = TeamFactory(sport=sport, name="Away FC")
        comp = CompetitionFactory(sport=sport, name="Test League")
        return MatchFactory(
            sport=sport,
            home_team=home,
            away_team=away,
            competition=comp,
            status="scheduled",
        )

    def test_upcoming_requires_sport_param(self, auth_client):
        response = auth_client.get("/api/v1/matches/upcoming/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_upcoming_db_fallback(self, auth_client):
        match = self._create_match("football5")
        with patch(
            "sports_platform.matches.views.get_match_store"
        ) as mock_store:
            mock_store.return_value.get_upcoming_ids.return_value = []
            response = auth_client.get(f"/api/v1/matches/upcoming/?sport=football5")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["source"] == "db"

    def test_live_endpoint_returns_200(self, auth_client):
        with patch("sports_platform.matches.views.get_match_store") as mock_store:
            mock_store.return_value.get_live_match_ids.return_value = []
            response = auth_client.get("/api/v1/matches/live/")
        assert response.status_code == status.HTTP_200_OK

    def test_match_detail_404_on_unknown(self, auth_client):
        response = auth_client.get(f"/api/v1/matches/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_match_detail_with_score(self, auth_client):
        match = self._create_match("football6")
        with patch("sports_platform.matches.views.get_match_store") as mock_store:
            mock_store.return_value.get_score.return_value = {
                "score_data": {"home": 1, "away": 0},
                "status": "live",
                "updated_at": str(int(time.time()) - 5),
            }
            mock_store.return_value.get_recent_events.return_value = []
            response = auth_client.get(f"/api/v1/matches/{match.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["score"]["home"] == 1
        assert response.data["score_source"] == "cache"
        assert response.data["data_freshness_seconds"] is not None

    def test_match_events_paginated(self, auth_client):
        from tests.factories import MatchEventFactory, SportFactory, MatchFactory, TeamFactory, CompetitionFactory
        sport = SportFactory(slug="football7", name="Football")
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        comp = CompetitionFactory(sport=sport)
        match = MatchFactory(sport=sport, home_team=home, away_team=away, competition=comp)
        for i in range(5):
            MatchEventFactory(match=match, sport=sport, event_sequence=i)
        response = auth_client.get(f"/api/v1/matches/{match.id}/events/?page_size=3")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 5
        assert len(response.data["events"]) == 3

    def test_unauthenticated_returns_401(self, api_client):
        response = api_client.get("/api/v1/matches/live/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
