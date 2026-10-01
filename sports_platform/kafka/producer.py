"""
Kafka Event Producer.

Singleton producer that wraps kafka-python's KafkaProducer.
All message values are serialized via Pydantic's model_dump_json().

Thread-safe: KafkaProducer itself is thread-safe; producer is instantiated
once and shared across all callers (ingestion workers, Celery tasks, etc.).
"""
import logging
from typing import Optional

from django.conf import settings

from sports_platform.kafka.events import (
    KafkaEvent,
    KafkaTopics,
    MatchDiscoveredEvent,
    MatchEventPublished,
    MatchStartedEvent,
    MatchCompletedEvent,
    ScoreUpdatedEvent,
    UserPreferenceUpdatedEvent,
)
from sports_platform.providers.base import ProviderMatch, ProviderMatchEvent, ProviderScore

logger = logging.getLogger(__name__)


class KafkaEventProducer:
    """
    Thread-safe Kafka producer with typed publish methods.

    Usage:
        producer = KafkaEventProducer()
        producer.publish_match_discovered(match, provider_name="api_football")
    """

    def __init__(self, bootstrap_servers: Optional[str] = None):
        from kafka import KafkaProducer

        servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self._producer = KafkaProducer(
            bootstrap_servers=servers,
            acks="all",           # Wait for all ISR replicas to acknowledge
            retries=3,
            linger_ms=5,          # Batch small messages for 5ms
            compression_type="gzip",
            request_timeout_ms=30_000,
        )
        logger.info("KafkaEventProducer initialized", extra={"servers": servers})

    # ── Core publish ─────────────────────────────────────────────────────────

    def publish(self, topic: str, event: KafkaEvent) -> None:
        """
        Serialize event to JSON and send to Kafka topic.
        Uses event_id as the message key for partition affinity.
        """
        payload = event.model_dump_json().encode("utf-8")
        key = event.event_id.encode("utf-8")
        try:
            future = self._producer.send(topic, key=key, value=payload)
            future.add_errback(self._on_send_error, topic=topic, event_id=event.event_id)
        except Exception as exc:
            logger.error(
                "Kafka publish failed",
                extra={
                    "topic": topic,
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error": str(exc),
                },
            )
            raise

    def _on_send_error(self, exc, topic: str, event_id: str):
        logger.error(
            "Kafka send error (async callback)",
            extra={"topic": topic, "event_id": event_id, "error": str(exc)},
        )

    def flush(self, timeout: float = 10.0):
        """Flush all pending messages. Call before shutdown."""
        self._producer.flush(timeout=timeout)

    def close(self):
        self._producer.close()

    # ── Typed publish methods ─────────────────────────────────────────────────

    def publish_match_discovered(
        self, match: ProviderMatch, provider_name: str
    ) -> None:
        event = MatchDiscoveredEvent.from_provider_match(match, provider_name)
        self.publish(KafkaTopics.MATCH_DISCOVERED, event)
        logger.debug(
            "Published match.discovered",
            extra={"provider_match_id": match.provider_match_id, "sport": match.sport},
        )

    def publish_match_started(
        self, provider_match_id: str, sport: str, internal_match_id: str, provider_name: str
    ) -> None:
        event = MatchStartedEvent(
            provider_name=provider_name,
            provider_match_id=provider_match_id,
            sport=sport,
            internal_match_id=internal_match_id,
        )
        self.publish(KafkaTopics.MATCH_STARTED, event)

    def publish_match_completed(
        self,
        provider_match_id: str,
        sport: str,
        internal_match_id: str,
        provider_name: str,
        final_score_data: dict,
    ) -> None:
        event = MatchCompletedEvent(
            provider_name=provider_name,
            provider_match_id=provider_match_id,
            sport=sport,
            internal_match_id=internal_match_id,
            final_score_data=final_score_data,
        )
        self.publish(KafkaTopics.MATCH_COMPLETED, event)

    def publish_score_updated(
        self, score: ProviderScore, internal_match_id: str, provider_name: str
    ) -> None:
        event = ScoreUpdatedEvent.from_provider_score(score, provider_name, internal_match_id)
        self.publish(KafkaTopics.SCORE_UPDATED, event)

    def publish_match_event(
        self,
        match_event: ProviderMatchEvent,
        internal_match_id: str,
        provider_name: str,
    ) -> None:
        event = MatchEventPublished.from_provider_event(
            match_event, provider_name, internal_match_id
        )
        self.publish(KafkaTopics.MATCH_EVENT, event)

    def publish_preference_updated(self, user_id: str, changed_sports: list) -> None:
        event = UserPreferenceUpdatedEvent(
            user_id=user_id,
            changed_sports=changed_sports,
        )
        self.publish(KafkaTopics.USER_PREFERENCE_UPDATED, event)


# ── Singleton ─────────────────────────────────────────────────────────────────

_producer: Optional[KafkaEventProducer] = None


def get_producer() -> KafkaEventProducer:
    """
    Return the singleton KafkaEventProducer instance.
    Initialized lazily so Django settings are available on first use.
    """
    global _producer
    if _producer is None:
        _producer = KafkaEventProducer()
    return _producer
