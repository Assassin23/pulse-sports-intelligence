"""
Pydantic event schemas for all Kafka topics.

Each event is a self-describing, versioned message with:
- event_id: unique UUID for deduplication
- event_type: discriminator for consumer routing
- schema_version: for forward/backward compatibility
- occurred_at: UTC timestamp of the event

Serialization (Producer):
    payload = event.model_dump_json().encode("utf-8")

Deserialization (Consumer):
    event = MatchDiscoveredEvent.model_validate_json(message.value)
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from sports_platform.providers.base import ProviderMatch, ProviderMatchEvent, ProviderScore


# ── Base Kafka Event Envelope ─────────────────────────────────────────────────

class KafkaEvent(BaseModel):
    """Base envelope for all Kafka messages."""
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    schema_version: str = "1.0"
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


# ── Match Lifecycle Events ────────────────────────────────────────────────────

class MatchDiscoveredEvent(KafkaEvent):
    """
    Topic:    sports.match.discovered
    Producer: SportsIngestionWorker (upcoming fixtures poll)
    Consumer: MatchProcessorConsumer → upserts to PostgreSQL matches table
    """
    event_type: Literal["match.discovered"] = "match.discovered"

    provider_name: str
    provider_match_id: str
    sport: str
    competition_name: str
    competition_provider_id: str
    home_team_name: str
    home_team_provider_id: str
    away_team_name: str
    away_team_provider_id: str
    scheduled_at: datetime
    status: str
    venue: Optional[str] = None
    round: Optional[str] = None
    season: Optional[str] = None

    @classmethod
    def from_provider_match(
        cls, match: ProviderMatch, provider_name: str
    ) -> "MatchDiscoveredEvent":
        return cls(
            provider_name=provider_name,
            **match.model_dump(exclude={"raw"}),
        )


class MatchStartedEvent(KafkaEvent):
    """
    Topic:    sports.match.started
    Producer: SportsIngestionWorker (live poll detects status → live)
    Consumer: ScoreProcessorConsumer → adds match_id to matches:live in Redis
    """
    event_type: Literal["match.started"] = "match.started"

    provider_name: str
    provider_match_id: str
    sport: str
    internal_match_id: str  # UUID of the match in our DB


class MatchCompletedEvent(KafkaEvent):
    """
    Topic:    sports.match.completed
    Producer: SportsIngestionWorker
    Consumer: ScoreProcessorConsumer → removes from matches:live, writes final score
    """
    event_type: Literal["match.completed"] = "match.completed"

    provider_name: str
    provider_match_id: str
    sport: str
    internal_match_id: str
    final_score_data: Dict[str, Any]


# ── Score Events ──────────────────────────────────────────────────────────────

class ScoreUpdatedEvent(KafkaEvent):
    """
    Topic:    sports.score.updated
    Producer: SportsIngestionWorker (live score poll, every ~10s)
    Consumer: ScoreProcessorConsumer → writes to Redis match:score:{id} + match_scores table
    """
    event_type: Literal["score.updated"] = "score.updated"

    provider_name: str
    provider_match_id: str
    internal_match_id: str
    sport: str
    score_data: Dict[str, Any]
    sequence_number: int
    source_timestamp: datetime

    @classmethod
    def from_provider_score(
        cls, score: ProviderScore, provider_name: str, internal_match_id: str
    ) -> "ScoreUpdatedEvent":
        return cls(
            provider_name=provider_name,
            internal_match_id=internal_match_id,
            **score.model_dump(),
        )


# ── Match Event Events ────────────────────────────────────────────────────────

class MatchEventPublished(KafkaEvent):
    """
    Topic:    sports.match.event
    Producer: SportsIngestionWorker (events poll)
    Consumer: EventProcessorConsumer → writes to match_events table + Redis sorted set
    """
    event_type: Literal["match.event"] = "match.event"

    provider_name: str
    provider_match_id: str
    internal_match_id: str
    sport: str
    event_type_detail: str  # 'goal', 'wicket', 'red_card', 'yellow_card', 'substitution'
    event_sequence: int
    occurred_at: Optional[datetime] = None
    minute: Optional[int] = None
    over_ball: Optional[str] = None
    player_name: Optional[str] = None
    player_provider_id: Optional[str] = None
    secondary_player_name: Optional[str] = None
    team_provider_id: Optional[str] = None
    description: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_provider_event(
        cls,
        event: ProviderMatchEvent,
        provider_name: str,
        internal_match_id: str,
    ) -> "MatchEventPublished":
        return cls(
            provider_name=provider_name,
            internal_match_id=internal_match_id,
            provider_match_id=event.provider_match_id,
            sport=event.sport,
            event_type_detail=event.event_type,
            event_sequence=event.event_sequence,
            occurred_at=event.occurred_at,
            minute=event.minute,
            over_ball=event.over_ball,
            player_name=event.player_name,
            player_provider_id=event.player_provider_id,
            secondary_player_name=event.secondary_player_name,
            team_provider_id=event.team_provider_id,
            description=event.description,
            extra=event.extra,
        )


# ── User Events ───────────────────────────────────────────────────────────────

class UserPreferenceUpdatedEvent(KafkaEvent):
    """
    Topic:    sports.user.preference.updated
    Producer: PreferenceService (on PUT /me/preferences or follow/unfollow)
    Consumer: FeedInvalidationConsumer → busts feed:{user_id} in Redis
    """
    event_type: Literal["user.preference.updated"] = "user.preference.updated"

    user_id: str
    changed_sports: list = Field(default_factory=list)


# ── Kafka Topic Names ─────────────────────────────────────────────────────────

class KafkaTopics:
    MATCH_DISCOVERED = "sports.match.discovered"
    MATCH_STARTED = "sports.match.started"
    MATCH_COMPLETED = "sports.match.completed"
    SCORE_UPDATED = "sports.score.updated"
    MATCH_EVENT = "sports.match.event"
    USER_PREFERENCE_UPDATED = "sports.user.preference.updated"

    # Dead Letter Queues — DLQ
    MATCH_DISCOVERED_DLQ = "sports.match.discovered.dlq"
    SCORE_UPDATED_DLQ = "sports.score.updated.dlq"
    MATCH_EVENT_DLQ = "sports.match.event.dlq"

    @classmethod
    def all_topics(cls) -> list:
        return [
            cls.MATCH_DISCOVERED,
            cls.MATCH_STARTED,
            cls.MATCH_COMPLETED,
            cls.SCORE_UPDATED,
            cls.MATCH_EVENT,
            cls.USER_PREFERENCE_UPDATED,
            cls.MATCH_DISCOVERED_DLQ,
            cls.SCORE_UPDATED_DLQ,
            cls.MATCH_EVENT_DLQ,
        ]
