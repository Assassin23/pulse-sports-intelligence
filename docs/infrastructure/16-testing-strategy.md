# 16. Testing Strategy

## 16.1 Test Pyramid

```
                ┌───────┐
                │  E2E  │  < 5% (slow, expensive)
               ─┼───────┼─
              │ Integr. │  ~30% (Kafka, Redis, DB)
             ─┼─────────┼─
            │    Unit    │  ~65% (fast, pure logic)
           ─────────────────
```

Target coverage: **> 80%** on business logic (services, consumers, providers, AI tools).

---

## 16.2 Unit Tests

### What to Unit Test

- Provider adapters: normalization/mapping logic
- Kafka event payloads: serialization/deserialization
- Score update logic: idempotency, sequence number handling
- Notification fanout: rule evaluation
- AI tools: input/output contracts
- Rate limiting: counter logic
- Odds normalization: format conversion
- Feed assembly: preference matching

```python
# tests/unit/test_score_processor.py

import pytest
from sports_platform.matches.processors import ScoreProcessor
from sports_platform.kafka.events import ScoreUpdatedEvent


class TestScoreProcessor:
    def test_score_update_applied_when_sequence_is_newer(self, mock_redis, mock_db):
        processor = ScoreProcessor(redis=mock_redis, db=mock_db)
        event = ScoreUpdatedEvent(
            match_id="match-123",
            score_data={"home_runs": 145, "away_runs": 0},
            sequence_number=892,
        )
        mock_redis.hget.return_value = b"891"  # Current stored sequence

        result = processor.process(event)

        assert result.updated is True
        mock_redis.hmset.assert_called_once()

    def test_score_update_skipped_when_sequence_is_older(self, mock_redis, mock_db):
        processor = ScoreProcessor(redis=mock_redis, db=mock_db)
        event = ScoreUpdatedEvent(
            match_id="match-123",
            score_data={"home_runs": 140},
            sequence_number=890,
        )
        mock_redis.hget.return_value = b"892"  # Stored sequence is newer

        result = processor.process(event)

        assert result.updated is False
        mock_redis.hmset.assert_not_called()

    def test_duplicate_event_skipped(self, mock_redis, mock_db):
        processor = ScoreProcessor(redis=mock_redis, db=mock_db)
        mock_redis.setnx.return_value = 0  # Already processed

        event = ScoreUpdatedEvent(match_id="match-123", sequence_number=892)
        result = processor.process(event)

        assert result.skipped is True
```

```python
# tests/unit/test_api_football_adapter.py

import pytest
from sports_platform.providers.adapters.api_football import ApiFootballAdapter


class TestApiFootballAdapter:
    def test_normalizes_status_correctly(self):
        adapter = ApiFootballAdapter(api_key="test")
        assert adapter.STATUS_MAP["1H"] == "live"
        assert adapter.STATUS_MAP["FT"] == "completed"
        assert adapter.STATUS_MAP["PST"] == "postponed"

    def test_normalizes_fixture_to_provider_match(self, raw_fixture_payload):
        adapter = ApiFootballAdapter(api_key="test")
        result = adapter._normalize_fixture(raw_fixture_payload)
        assert result.sport == "football"
        assert result.status == "live"
        assert result.home_team_name == "Chelsea FC"
```

---

## 16.3 API Integration Tests

Use `pytest` + `django.test.Client` + a test PostgreSQL database:

```python
# tests/api/test_matches.py

import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from tests.factories import UserFactory, MatchFactory, TeamFactory


class TestMatchesAPI(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_get_live_matches_returns_200(self):
        match = MatchFactory(status="live")
        response = self.client.get("/api/v1/matches/live")
        assert response.status_code == 200
        assert len(response.data["matches"]) == 1

    def test_get_match_detail_includes_score(self):
        match = MatchFactory(status="live")
        response = self.client.get(f"/api/v1/matches/{match.id}")
        assert response.status_code == 200
        assert "score" in response.data

    def test_unauthenticated_request_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/v1/feed")
        assert response.status_code == 401

    def test_ai_ask_returns_answer(self, mock_langgraph):
        match = MatchFactory(status="live")
        mock_langgraph.return_value = {"final_answer": "RCB are winning"}
        response = self.client.post(
            f"/api/v1/ai/matches/{match.id}/ask",
            {"question": "How is RCB doing?"},
        )
        assert response.status_code == 200
        assert "answer" in response.data
```

---

## 16.4 Kafka Integration Tests

Use `testcontainers` to spin up a real Kafka instance in tests:

```python
# tests/integration/test_kafka_consumers.py

import pytest
from testcontainers.kafka import KafkaContainer
from sports_platform.kafka.consumers.score_processor import ScoreProcessorConsumer
from sports_platform.kafka.producers import KafkaEventProducer


@pytest.fixture(scope="module")
def kafka_container():
    with KafkaContainer() as kafka:
        yield kafka


class TestScoreProcessorKafkaIntegration:
    def test_score_update_processed_end_to_end(
        self, kafka_container, db, redis_client
    ):
        bootstrap_servers = kafka_container.get_bootstrap_server()
        producer = KafkaEventProducer(bootstrap_servers=bootstrap_servers)
        consumer = ScoreProcessorConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id="test-group",
        )

        # Publish a score update event
        producer.publish({
            "event_type": "sports.score.updated",
            "event_id": "test-event-123",
            "payload": {
                "match_id": "test-match-1",
                "sport": "cricket",
                "score": {"home_runs": 145, "wickets": 3},
                "sequence_number": 892,
            }
        })

        # Consumer processes it
        consumer.run_once()  # Process one message

        # Verify Redis was updated
        score = redis_client.hgetall("match:score:test-match-1")
        assert int(score[b"home_score"]) == 145
        assert int(score[b"sequence_number"]) == 892
```

---

## 16.5 Redis Integration Tests

```python
# tests/integration/test_redis_state.py

import pytest
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="module")
def redis_container():
    with RedisContainer() as redis:
        yield redis


class TestRedisMatchState:
    def test_score_update_atomic_sequence_check(self, redis_container):
        client = redis_container.get_client()
        
        # Set initial state
        client.hset("match:score:test-1", mapping={"sequence_number": "891"})
        
        # Execute Lua script (newer sequence) → should update
        result = run_score_update_lua(client, "test-1", {"home_score": 145}, 892)
        assert result == 1
        
        # Execute Lua script (older sequence) → should skip
        result = run_score_update_lua(client, "test-1", {"home_score": 140}, 890)
        assert result == 0
        
        # Score should still be 145 (not overwritten)
        score = client.hget("match:score:test-1", "home_score")
        assert int(score) == 145
```

---

## 16.6 WebSocket Tests

```python
# tests/websocket/test_ws_gateway.py

import pytest
import asyncio
import websockets
from fastapi.testclient import TestClient
from ws_gateway.main import app


class TestWebSocketGateway:
    @pytest.mark.asyncio
    async def test_websocket_receives_score_update(self, test_redis, mock_jwt):
        """Test that a score update published to Redis is delivered via WebSocket."""
        
        # Connect client
        async with websockets.connect(
            f"ws://localhost:8001/ws/match/test-match-1?token={mock_jwt}"
        ) as ws:
            # Receive initial state
            initial = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert '"type": "initial_state"' in initial
            
            # Simulate processor publishing to Redis pub/sub
            test_redis.publish(
                "ws:match:test-match-1",
                '{"type": "score_updated", "score": {"home_runs": 145}}'
            )
            
            # Client should receive it
            update = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert '"type": "score_updated"' in update

    @pytest.mark.asyncio
    async def test_unauthorized_websocket_rejected(self):
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc:
            async with websockets.connect(
                "ws://localhost:8001/ws/match/test?token=invalid-token"
            ) as ws:
                await ws.recv()
        assert exc.value.code == 4001
```

---

## 16.7 AI Tool Tests

```python
# tests/ai/test_ai_tools.py

import pytest
from sports_platform.ai.tools import get_live_score, get_match_events


class TestAITools:
    def test_get_live_score_returns_real_data(self, mock_redis_with_score):
        """AI tool must return data from Redis, not LLM."""
        score = get_live_score("test-match-1")
        assert score["home_runs"] == 145
        assert "llm_generated" not in score  # Must be tool data

    def test_get_live_score_handles_missing_match(self):
        """Tool must return structured error, not raise exception."""
        score = get_live_score("non-existent-match")
        assert score["error"] == "match_not_found"

    def test_get_match_events_returns_ordered_list(self, db_with_events):
        events = get_match_events("test-match-1", last_n=5)
        sequences = [e["sequence"] for e in events]
        assert sequences == sorted(sequences)  # Must be in order
```

---

## 16.8 RAG Evaluation

```python
# tests/rag/test_rag_retrieval.py

class TestRAGRetrieval:
    """
    RAG evaluation tests using golden question-answer pairs.
    Tests retrieval quality, not LLM quality.
    """

    GOLDEN_PAIRS = [
        {
            "question": "What are the IPL Powerplay rules?",
            "expected_doc_type": "competition_rules",
            "expected_keyword": "powerplay",
        },
        {
            "question": "Tell me about Jasprit Bumrah's bowling style",
            "expected_doc_type": "player_profile",
            "expected_keyword": "bumrah",
        },
    ]

    def test_retrieval_returns_relevant_docs(self, rag_retriever, test_rag_db):
        for pair in self.GOLDEN_PAIRS:
            chunks = rag_retriever.retrieve(
                query=pair["question"],
                sport="cricket",
            )
            
            # At least one chunk should be of the expected document type
            doc_types = [c.document_type for c in chunks]
            assert pair["expected_doc_type"] in doc_types
            
            # At least one chunk should contain the keyword
            all_text = " ".join(c.content.lower() for c in chunks)
            assert pair["expected_keyword"] in all_text
```

---

## 16.9 Load Testing

Using **Locust** for load testing:

```python
# tests/load/locustfile.py

from locust import HttpUser, task, between, events
import websocket
import json


class SportsAPIUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Login
        resp = self.client.post("/api/v1/auth/login", json={
            "email": f"test+{self.user_id}@example.com",
            "password": "TestPass123!"
        })
        self.token = resp.json()["tokens"]["access"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    @task(5)
    def view_feed(self):
        self.client.get("/api/v1/feed")

    @task(3)
    def view_live_matches(self):
        self.client.get("/api/v1/matches/live")

    @task(2)
    def view_match_detail(self):
        self.client.get(f"/api/v1/matches/{self.match_id}")

    @task(1)
    def ask_ai(self):
        self.client.post(
            f"/api/v1/ai/matches/{self.match_id}/ask",
            json={"question": "What's the current score?"}
        )


# Load test targets:
# - 1K concurrent users: all endpoints < 200ms p99
# - 1K concurrent WebSocket connections: stable, no memory leak
# - 10K messages/min score updates: consumer lag < 500ms
```

---

## 16.10 Test Utilities & Factories

```python
# tests/factories.py

import factory
from sports_platform.users.models import User
from sports_platform.matches.models import Match, Team


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    password = factory.PostGenerationMethodCall("set_password", "TestPass123!")


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    name = factory.Sequence(lambda n: f"Team {n}")
    sport = factory.SubFactory(SportFactory)


class MatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Match

    status = "scheduled"
    home_team = factory.SubFactory(TeamFactory)
    away_team = factory.SubFactory(TeamFactory)
    sport = factory.SubFactory(SportFactory)
    competition = factory.SubFactory(CompetitionFactory)
    scheduled_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=1))
```
