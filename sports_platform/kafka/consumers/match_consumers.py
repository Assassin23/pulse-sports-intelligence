"""
Kafka consumers for match processing.

MatchProcessorConsumer:  match.discovered → PostgreSQL matches table
ScoreProcessorConsumer:  score.updated → Redis + PostgreSQL match_scores
EventProcessorConsumer:  match.event → PostgreSQL match_events + Redis sorted set
"""
import logging
from datetime import datetime, timezone

from django.db import transaction, IntegrityError

from sports_platform.kafka.base_consumer import (
    BaseKafkaConsumer,
    PermanentConsumerError,
    TransientConsumerError,
)
from sports_platform.kafka.events import (
    KafkaTopics,
    MatchDiscoveredEvent,
    MatchEventPublished,
    MatchStartedEvent,
    MatchCompletedEvent,
    ScoreUpdatedEvent,
)
from sports_platform.matches.redis_store import get_match_store
from sports_platform.providers.mapping_service import EntityMappingService

logger = logging.getLogger(__name__)


# ── Match Processor (Milestone 3) ─────────────────────────────────────────────

class MatchProcessorConsumer(BaseKafkaConsumer):
    """
    Consumes: sports.match.discovered
    Action:   Resolves provider entity IDs → internal UUIDs,
              creates Match row if not exists,
              caches metadata in Redis for fast API reads.
    """

    event_class = MatchDiscoveredEvent
    topics = [KafkaTopics.MATCH_DISCOVERED]
    consumer_group_id = "match-processor"
    dlq_topic = KafkaTopics.MATCH_DISCOVERED_DLQ

    def handle(self, event: MatchDiscoveredEvent) -> None:
        from sports_platform.matches.models import Match, MatchStatus
        from sports_platform.sports.models import Sport

        # ── Resolve sport ─────────────────────────────────────────────────────
        try:
            sport = Sport.objects.get(slug=event.sport, is_active=True)
        except Sport.DoesNotExist:
            raise PermanentConsumerError(
                f"Unknown sport slug '{event.sport}' in match.discovered event"
            )

        # ── Resolve / upsert competition ──────────────────────────────────────
        competition = EntityMappingService.upsert_competition(
            provider_name=event.provider_name,
            provider_competition_id=event.competition_provider_id,
            sport=sport,
            competition_name=event.competition_name,
            season=event.season or "",
        )

        # ── Resolve / upsert teams ────────────────────────────────────────────
        home_team = EntityMappingService.upsert_team(
            provider_name=event.provider_name,
            provider_team_id=event.home_team_provider_id,
            sport=sport,
            team_name=event.home_team_name,
        )
        away_team = EntityMappingService.upsert_team(
            provider_name=event.provider_name,
            provider_team_id=event.away_team_provider_id,
            sport=sport,
            team_name=event.away_team_name,
        )

        # ── Upsert match ──────────────────────────────────────────────────────
        try:
            with transaction.atomic():
                match, created = Match.objects.get_or_create(
                    source_provider=event.provider_name,
                    provider_match_id=event.provider_match_id,
                    defaults={
                        "sport": sport,
                        "competition": competition,
                        "home_team": home_team,
                        "away_team": away_team,
                        "scheduled_at": event.scheduled_at,
                        "status": event.status,
                        "venue": event.venue or "",
                        "round": event.round or "",
                    },
                )
        except Exception as exc:
            raise TransientConsumerError(f"DB error upserting match: {exc}") from exc

        # ── Cache metadata in Redis ───────────────────────────────────────────
        store = get_match_store()
        store.cache_match_meta(
            match_id=str(match.id),
            meta={
                "sport": event.sport,
                "competition_id": str(competition.id),
                "competition_name": event.competition_name,
                "home_team_id": str(home_team.id),
                "home_team_name": event.home_team_name,
                "away_team_id": str(away_team.id),
                "away_team_name": event.away_team_name,
                "scheduled_at": event.scheduled_at.isoformat(),
                "status": event.status,
                "venue": event.venue or "",
                "provider_match_id": event.provider_match_id,
                "source_provider": event.provider_name,
            },
        )
        # Add to upcoming Redis index
        store.add_upcoming(
            sport_slug=event.sport,
            match_id=str(match.id),
            scheduled_at=event.scheduled_at,
        )

        action = "created" if created else "already existed"
        logger.info(
            f"Match {action}",
            extra={
                "match_id": str(match.id),
                "provider_match_id": event.provider_match_id,
                "home": event.home_team_name,
                "away": event.away_team_name,
            },
        )

        # Register provider mapping for the match itself
        EntityMappingService.register(
            provider_name=event.provider_name,
            entity_type="match",
            provider_entity_id=event.provider_match_id,
            internal_entity_id=match.id,
        )


# ── Score Processor (Milestone 4) ────────────────────────────────────────────

class ScoreProcessorConsumer(BaseKafkaConsumer):
    """
    Consumes: sports.score.updated, sports.match.started, sports.match.completed
    Action:   Updates Redis match:score:{id} (idempotent via Lua script)
              Updates PostgreSQL match_scores table
              Manages matches:live Redis set
    """

    event_class = ScoreUpdatedEvent
    topics = [
        KafkaTopics.SCORE_UPDATED,
        KafkaTopics.MATCH_STARTED,
        KafkaTopics.MATCH_COMPLETED,
    ]
    consumer_group_id = "score-processor"
    dlq_topic = KafkaTopics.SCORE_UPDATED_DLQ

    def handle(self, event) -> None:
        if isinstance(event, MatchStartedEvent):
            self._handle_started(event)
        elif isinstance(event, MatchCompletedEvent):
            self._handle_completed(event)
        elif isinstance(event, ScoreUpdatedEvent):
            self._handle_score(event)

    def _handle_score(self, event: ScoreUpdatedEvent) -> None:
        from sports_platform.matches.models import Match, MatchScore

        # ── Redis update (Lua atomic idempotency) ─────────────────────────────
        store = get_match_store()
        store.update_score(
            match_id=event.internal_match_id,
            score_data=event.score_data,
            sequence_number=event.sequence_number,
            status="live",
        )

        # ── PostgreSQL update (best-effort durability) ────────────────────────
        try:
            with transaction.atomic():
                MatchScore.objects.update_or_create(
                    match_id=event.internal_match_id,
                    defaults={
                        "score_data": event.score_data,
                        "sequence_number": event.sequence_number,
                    },
                )
        except Match.DoesNotExist:
            raise PermanentConsumerError(
                f"Match {event.internal_match_id} not found for score update"
            )
        except Exception as exc:
            # Redis already updated; DB failure is transient
            raise TransientConsumerError(f"DB score update failed: {exc}") from exc

    def _handle_started(self, event: MatchStartedEvent) -> None:
        from sports_platform.matches.models import Match

        store = get_match_store()
        store.add_to_live(event.internal_match_id)
        try:
            Match.objects.filter(id=event.internal_match_id).update(
                status="live",
                started_at=datetime.now(tz=timezone.utc),
            )
        except Exception as exc:
            raise TransientConsumerError(f"DB match start update failed: {exc}") from exc

    def _handle_completed(self, event: MatchCompletedEvent) -> None:
        from sports_platform.matches.models import Match, MatchScore

        store = get_match_store()
        store.remove_from_live(event.internal_match_id)
        store.expire_score_fast(event.internal_match_id)
        try:
            with transaction.atomic():
                Match.objects.filter(id=event.internal_match_id).update(
                    status="completed",
                    completed_at=datetime.now(tz=timezone.utc),
                )
                MatchScore.objects.update_or_create(
                    match_id=event.internal_match_id,
                    defaults={"score_data": event.final_score_data},
                )
        except Exception as exc:
            raise TransientConsumerError(f"DB match complete update failed: {exc}") from exc


# ── Event Processor (Milestone 4) ────────────────────────────────────────────

class EventProcessorConsumer(BaseKafkaConsumer):
    """
    Consumes: sports.match.event
    Action:   Writes to PostgreSQL match_events (dedup via unique constraint)
              Pushes to Redis match:events:recent:{id} sorted set
    """

    event_class = MatchEventPublished
    topics = [KafkaTopics.MATCH_EVENT]
    consumer_group_id = "event-processor"
    dlq_topic = KafkaTopics.MATCH_EVENT_DLQ

    def handle(self, event: MatchEventPublished) -> None:
        from sports_platform.matches.models import Match, MatchEvent
        from sports_platform.sports.models import Sport

        # ── PostgreSQL write ───────────────────────────────────────────────────
        try:
            sport = Sport.objects.get(slug=event.sport)
        except Sport.DoesNotExist:
            raise PermanentConsumerError(f"Unknown sport: {event.sport}")

        try:
            with transaction.atomic():
                MatchEvent.objects.get_or_create(
                    match_id=event.internal_match_id,
                    source_provider=event.provider_name,
                    event_sequence=event.event_sequence,
                    defaults={
                        "sport": sport,
                        "event_type": event.event_type_detail,
                        "occurred_at": event.occurred_at,
                        "minute": event.minute,
                        "over_ball": event.over_ball or "",
                        "description": event.description or "",
                        "event_data": event.extra,
                    },
                )
        except Exception as exc:
            raise TransientConsumerError(f"DB event write failed: {exc}") from exc

        # ── Redis recent events push ───────────────────────────────────────────
        store = get_match_store()
        store.push_event(
            match_id=event.internal_match_id,
            event_sequence=event.event_sequence,
            event_payload={
                "event_type": event.event_type_detail,
                "minute": event.minute,
                "over_ball": event.over_ball,
                "player_name": event.player_name,
                "description": event.description,
                "team_provider_id": event.team_provider_id,
            },
        )
