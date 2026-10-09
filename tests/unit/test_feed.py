"""
Tests for Milestone 5: Personalized Feed.

- FeedService: feed assembly, ranking, followed entity matching, fallback
- Redis caching: 5-minute TTL, hit/miss flow, invalidation
- Live enrichment: score and latest event from Redis attached with freshness
- Cursor pagination: next_cursor, has_more, offset handling
- FeedInvalidationConsumer: busts Redis feed cache on sports.user.preference.updated
- GET /api/v1/feed: API endpoint authentication and response schema
"""
import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from sports_platform.feed.redis_store import FeedRedisStore
from sports_platform.feed.services import FeedService
from sports_platform.kafka.consumers.feed_consumers import FeedInvalidationConsumer
from sports_platform.kafka.events import UserPreferenceUpdatedEvent
from sports_platform.preferences.services import PreferenceService
from tests.factories import (
    CompetitionFactory,
    MatchEventFactory,
    MatchFactory,
    SportFactory,
    TeamFactory,
    UserFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory(email="feeduser@example.com", username="feeduser")


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def fake_feed_store():
    store = FeedRedisStore.__new__(FeedRedisStore)
    store._redis = fakeredis.FakeRedis(decode_responses=True)
    return store


@pytest.mark.django_db
class TestFeedServiceAssembly:
    def test_feed_includes_followed_team_matches(self, user, fake_feed_store):
        sport = SportFactory(slug="football", name="Football")
        team1 = TeamFactory(sport=sport, name="Arsenal", short_name="ARS")
        team2 = TeamFactory(sport=sport, name="Chelsea", short_name="CHE")
        team3 = TeamFactory(sport=sport, name="Liverpool", short_name="LIV")

        PreferenceService.follow_entity(user, "football", "team", team1.id)

        match1 = MatchFactory(
            sport=sport, home_team=team1, away_team=team2, status="scheduled"
        )
        match2 = MatchFactory(
            sport=sport, home_team=team2, away_team=team3, status="scheduled"
        )

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            feed = FeedService.assemble_feed(user)

        match_ids = [str(m["id"]) for m in feed["matches"]]
        assert str(match1.id) in match_ids

        # Verify relevance tags
        ars_match = next(m for m in feed["matches"] if str(m["id"]) == str(match1.id))
        assert "team:ARS" in ars_match["relevance_tags"] or "team:Arsenal" in ars_match["relevance_tags"]

    def test_live_matches_appear_first(self, user, fake_feed_store):
        sport = SportFactory(slug="cricket", name="Cricket")
        team_a = TeamFactory(sport=sport, name="RCB", short_name="RCB")
        team_b = TeamFactory(sport=sport, name="CSK", short_name="CSK")

        PreferenceService.follow_entity(user, "cricket", "team", team_a.id)

        scheduled_match = MatchFactory(
            sport=sport, home_team=team_a, away_team=team_b, status="scheduled"
        )
        live_match = MatchFactory(
            sport=sport, home_team=team_b, away_team=team_a, status="live"
        )

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            feed = FeedService.assemble_feed(user)

        assert len(feed["matches"]) >= 2
        # First match should be the live one
        assert feed["matches"][0]["id"] == live_match.id
        assert feed["matches"][0]["status"] == "live"

    def test_status_filter_works(self, user, fake_feed_store):
        sport = SportFactory(slug="football", name="Football")
        team = TeamFactory(sport=sport, name="Real Madrid", short_name="RMA")
        opp = TeamFactory(sport=sport, name="Barcelona", short_name="FCB")

        PreferenceService.follow_entity(user, "football", "team", team.id)

        m_live = MatchFactory(sport=sport, home_team=team, away_team=opp, status="live")
        m_scheduled = MatchFactory(sport=sport, home_team=team, away_team=opp, status="scheduled")
        m_completed = MatchFactory(sport=sport, home_team=team, away_team=opp, status="completed")

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            feed_live_only = FeedService.assemble_feed(user, status_filter="live")
            feed_upcoming_only = FeedService.assemble_feed(user, status_filter="upcoming")

        live_ids = [str(m["id"]) for m in feed_live_only["matches"]]
        assert str(m_live.id) in live_ids
        assert str(m_scheduled.id) not in live_ids
        assert str(m_completed.id) not in live_ids

        upcoming_ids = [str(m["id"]) for m in feed_upcoming_only["matches"]]
        assert str(m_scheduled.id) in upcoming_ids
        assert str(m_live.id) not in upcoming_ids

    def test_live_enrichment_from_redis(self, user, fake_feed_store):
        sport = SportFactory(slug="football", name="Football")
        team = TeamFactory(sport=sport, name="Bayern", short_name="FCB")
        PreferenceService.follow_entity(user, "football", "team", team.id)

        match = MatchFactory(sport=sport, home_team=team, status="live")

        mock_match_store = MagicMock()
        mock_match_store.get_score.return_value = {
            "score_data": {"home": 3, "away": 1},
            "status": "live",
            "updated_at": str(int(time.time()) - 10),
        }
        mock_match_store.get_recent_events.return_value = [
            {
                "event_type": "goal",
                "description": "Kane scores!",
                "minute": 72,
                "player_name": "Harry Kane",
            }
        ]

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            with patch("sports_platform.feed.services.get_match_store", return_value=mock_match_store):
                feed = FeedService.assemble_feed(user)

        m_data = feed["matches"][0]
        assert m_data["score"]["home"] == 3
        assert m_data["score"]["away"] == 1
        assert m_data["last_event"]["description"] == "Kane scores!"
        assert m_data["data_freshness_seconds"] is not None
        assert m_data["data_freshness_seconds"] >= 0


@pytest.mark.django_db
class TestFeedCachingAndPagination:
    def test_feed_cached_in_redis_and_hit_on_subsequent_call(self, user, fake_feed_store):
        sport = SportFactory(slug="tennis", name="Tennis")
        player_team = TeamFactory(sport=sport, name="Djokovic")
        PreferenceService.follow_entity(user, "tennis", "team", player_team.id)

        MatchFactory(sport=sport, home_team=player_team, status="scheduled")

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            # First call -> cache miss, populates Redis
            feed1 = FeedService.assemble_feed(user)
            # Check Redis key exists
            cached_raw = fake_feed_store.get_feed(str(user.id))
            assert cached_raw is not None
            assert len(cached_raw["matches"]) == 1

            # Second call -> cache hit
            feed2 = FeedService.assemble_feed(user)
            assert feed1 == feed2

    def test_feed_cache_invalidated_by_preference_update(self, user, fake_feed_store):
        sport = SportFactory(slug="cricket", name="Cricket")
        team = TeamFactory(sport=sport, name="India", short_name="IND")

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            FeedService.assemble_feed(user)
            assert fake_feed_store.get_feed(str(user.id)) is not None

            # Following a team triggers cache invalidation
            PreferenceService.follow_entity(user, "cricket", "team", team.id)
            assert fake_feed_store.get_feed(str(user.id)) is None

    def test_feed_invalidation_consumer(self, fake_feed_store):
        user_id = str(uuid.uuid4())
        fake_feed_store.cache_feed(user_id, {"matches": [], "pagination": {"has_more": False}})
        assert fake_feed_store.get_feed(user_id) is not None

        consumer = FeedInvalidationConsumer.__new__(FeedInvalidationConsumer)
        event = UserPreferenceUpdatedEvent(user_id=user_id, change_type="follow")

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            consumer.handle(event)

        assert fake_feed_store.get_feed(user_id) is None

    def test_cursor_pagination(self, user, fake_feed_store):
        sport = SportFactory(slug="football", name="Football")
        team = TeamFactory(sport=sport, name="Juventus")
        PreferenceService.follow_entity(user, "football", "team", team.id)

        for i in range(5):
            MatchFactory(sport=sport, home_team=team, status="scheduled")

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            # Page 1 (page_size=2)
            page1 = FeedService.assemble_feed(user, page_size=2)
            assert len(page1["matches"]) == 2
            assert page1["pagination"]["has_more"] is True
            cursor1 = page1["pagination"]["next_cursor"]
            assert cursor1 is not None

            # Page 2
            page2 = FeedService.assemble_feed(user, cursor=cursor1, page_size=2)
            assert len(page2["matches"]) == 2
            assert page2["pagination"]["has_more"] is True
            cursor2 = page2["pagination"]["next_cursor"]

            # Page 3 (final)
            page3 = FeedService.assemble_feed(user, cursor=cursor2, page_size=2)
            assert len(page3["matches"]) == 1
            assert page3["pagination"]["has_more"] is False
            assert page3["pagination"]["next_cursor"] is None


@pytest.mark.django_db
class TestFeedAPI:
    def test_feed_endpoint_unauthenticated_returns_401(self, api_client):
        response = api_client.get("/api/v1/feed/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_feed_endpoint_authenticated_returns_200(self, auth_client, user, fake_feed_store):
        sport = SportFactory(slug="football", name="Football")
        team = TeamFactory(sport=sport, name="Liverpool")
        PreferenceService.follow_entity(user, "football", "team", team.id)
        MatchFactory(sport=sport, home_team=team, status="live")

        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            response = auth_client.get("/api/v1/feed/")

        assert response.status_code == status.HTTP_200_OK
        assert "matches" in response.data
        assert "pagination" in response.data
        assert len(response.data["matches"]) >= 1
        assert response.data["matches"][0]["status"] == "live"
        assert "relevance_tags" in response.data["matches"][0]

    def test_feed_endpoint_query_params(self, auth_client, user, fake_feed_store):
        with patch("sports_platform.feed.services.get_feed_store", return_value=fake_feed_store):
            response = auth_client.get("/api/v1/feed/?status=live,upcoming&page_size=10")

        assert response.status_code == status.HTTP_200_OK
        assert "matches" in response.data
        assert "pagination" in response.data
