"""
Sports Ingestion Worker.

Polls external data providers and publishes events to Kafka.
Runs as Celery Beat periodic tasks.

Responsibilities:
  - Poll upcoming fixtures → publish match.discovered
  - Poll live matches      → detect status transitions (started/completed)
  - Poll live scores       → publish score.updated
  - Poll match events      → publish match.event

Circuit breaker wraps all provider calls.
Stale data (from Redis) is served to API consumers if provider is unavailable.
"""
import logging
from datetime import datetime, timezone

from sports_platform.kafka.producer import get_producer
from sports_platform.matches.redis_store import get_match_store
from sports_platform.providers.base import MatchStatus, ProviderCircuitOpenError
from sports_platform.providers.mapping_service import EntityMappingService
from sports_platform.providers.registry import get_registry

logger = logging.getLogger(__name__)


class SportsIngestionWorker:
    """
    Polls a sport/provider pair and publishes normalized Kafka events.
    Does NOT write to PostgreSQL or Redis directly — that is the consumer's job.

    Usage (from Celery task):
        worker = SportsIngestionWorker(sport="football", provider_name="api_football")
        worker.ingest_upcoming()
        worker.ingest_live()
    """

    def __init__(self, sport: str, provider_name: str):
        self.sport = sport
        self.provider_name = provider_name
        self._registry = get_registry()
        self._producer = get_producer()
        self._store = get_match_store()

    def _get_provider(self):
        return self._registry.get_primary_provider(self.sport)

    def _call_provider(self, func, *args, **kwargs):
        """Wrap provider call in its circuit breaker."""
        provider = self._get_provider()
        cb = self._registry.get_circuit_breaker(self.provider_name)
        if cb:
            return cb.call(func, *args, **kwargs)
        return func(*args, **kwargs)

    # ── Upcoming fixture ingestion ────────────────────────────────────────────

    def ingest_upcoming(self, days_ahead: int = 3) -> int:
        """
        Fetch upcoming fixtures and publish match.discovered events.
        Returns number of events published.
        """
        try:
            provider = self._get_provider()
            fixtures = self._call_provider(
                provider.fetch_upcoming_fixtures, self.sport, days_ahead
            )
        except ProviderCircuitOpenError:
            logger.warning(
                "Circuit OPEN — skipping upcoming fixture poll",
                extra={"sport": self.sport, "provider": self.provider_name},
            )
            return 0
        except Exception as exc:
            logger.error(
                "Provider error on upcoming fixtures",
                extra={"sport": self.sport, "error": str(exc)},
            )
            return 0

        published = 0
        for fixture in fixtures:
            try:
                self._producer.publish_match_discovered(fixture, self.provider_name)
                published += 1
            except Exception as exc:
                logger.error(
                    "Failed to publish match.discovered",
                    extra={"provider_match_id": fixture.provider_match_id, "error": str(exc)},
                )

        logger.info(
            "Upcoming fixtures ingested",
            extra={"sport": self.sport, "total": len(fixtures), "published": published},
        )
        return published

    # ── Live match polling ────────────────────────────────────────────────────

    def ingest_live(self) -> int:
        """
        Fetch all live matches, detect status transitions, publish score/event updates.
        Returns number of score events published.
        """
        try:
            provider = self._get_provider()
            live_matches = self._call_provider(provider.fetch_live_matches, self.sport)
        except ProviderCircuitOpenError:
            logger.warning(
                "Circuit OPEN — skipping live match poll",
                extra={"sport": self.sport, "provider": self.provider_name},
            )
            return 0
        except Exception as exc:
            logger.error(
                "Provider error on live matches",
                extra={"sport": self.sport, "error": str(exc)},
            )
            return 0

        published = 0
        for match in live_matches:
            internal_id = EntityMappingService.resolve(
                provider_name=self.provider_name,
                entity_type="match",
                provider_entity_id=match.provider_match_id,
            )
            if not internal_id:
                # Match not yet in our DB — publish discovery first
                try:
                    self._producer.publish_match_discovered(match, self.provider_name)
                except Exception:
                    pass
                continue

            internal_match_id = str(internal_id)

            # ── Detect match started ──────────────────────────────────────────
            if match.status == MatchStatus.LIVE:
                self._check_and_publish_started(match, internal_match_id)

            # ── Fetch and publish live score ──────────────────────────────────
            try:
                score = self._call_provider(
                    provider.fetch_live_score, match.provider_match_id
                )
                if score:
                    self._producer.publish_score_updated(
                        score, internal_match_id, self.provider_name
                    )
                    published += 1
            except Exception as exc:
                logger.error(
                    "Score fetch failed",
                    extra={"provider_match_id": match.provider_match_id, "error": str(exc)},
                )

            # ── Fetch and publish match events ────────────────────────────────
            try:
                events = self._call_provider(
                    provider.fetch_match_events, match.provider_match_id
                )
                for evt in events:
                    self._producer.publish_match_event(evt, internal_match_id, self.provider_name)
            except Exception as exc:
                logger.warning(
                    "Event fetch failed",
                    extra={"provider_match_id": match.provider_match_id, "error": str(exc)},
                )

            # ── Detect match completed ────────────────────────────────────────
            if match.status == MatchStatus.COMPLETED:
                self._check_and_publish_completed(match, internal_match_id)

        return published

    def _check_and_publish_started(self, match, internal_match_id: str) -> None:
        """Publish match.started if match is now live but wasn't tracked yet."""
        live_ids = self._store.get_live_match_ids()
        if internal_match_id not in live_ids:
            try:
                self._producer.publish_match_started(
                    provider_match_id=match.provider_match_id,
                    sport=self.sport,
                    internal_match_id=internal_match_id,
                    provider_name=self.provider_name,
                )
            except Exception as exc:
                logger.error("Failed to publish match.started", extra={"error": str(exc)})

    def _check_and_publish_completed(self, match, internal_match_id: str) -> None:
        """Publish match.completed if match finished and is still in live set."""
        live_ids = self._store.get_live_match_ids()
        if internal_match_id in live_ids:
            try:
                self._producer.publish_match_completed(
                    provider_match_id=match.provider_match_id,
                    sport=self.sport,
                    internal_match_id=internal_match_id,
                    provider_name=self.provider_name,
                    final_score_data={},  # Will be filled by score consumer
                )
            except Exception as exc:
                logger.error("Failed to publish match.completed", extra={"error": str(exc)})
