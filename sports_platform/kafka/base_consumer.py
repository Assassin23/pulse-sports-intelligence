"""
Base Kafka consumer with at-least-once delivery, deduplication, and DLQ support.

Design:
  - Manual offset commit: only commits AFTER successful processing
  - Transient errors: log + sleep (does NOT commit → replays on restart)
  - Permanent errors: send to DLQ → commit (prevents partition blocking)
  - Deduplication: Redis SETNX with TTL for event_id idempotency
"""
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Type

from django.conf import settings

from sports_platform.kafka.events import KafkaEvent

logger = logging.getLogger(__name__)

# Max backoff for transient errors (seconds)
MAX_BACKOFF_SECONDS = 60


class PermanentConsumerError(Exception):
    """Message cannot be processed regardless of retries. Goes to DLQ."""
    pass


class TransientConsumerError(Exception):
    """Temporary failure. Consumer will retry after backoff."""
    pass


class BaseKafkaConsumer(ABC):
    """
    Base consumer with:
      - Manual commit for at-least-once delivery
      - Event deduplication via Redis (event_id SETNX with 24h TTL)
      - DLQ routing for permanent failures
      - Exponential backoff for transient failures
    """

    event_class: Type[KafkaEvent]   # Subclass must declare this
    topics: list[str]               # Subclass must declare this
    consumer_group_id: str          # Subclass must declare this
    dlq_topic: Optional[str] = None

    def __init__(self):
        from kafka import KafkaConsumer
        import redis as redis_lib

        self._consumer = KafkaConsumer(
            *self.topics,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.consumer_group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,   # Manual commit for at-least-once
            value_deserializer=None,    # We deserialize manually via Pydantic
            consumer_timeout_ms=1000,   # Allows graceful shutdown checks
        )
        self._redis = redis_lib.Redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
        self._running = False
        self._backoff_count = 0
        logger.info(
            "Consumer initialized",
            extra={"group": self.consumer_group_id, "topics": self.topics},
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        """Main consumer loop. Blocks until stop() is called."""
        self._running = True
        logger.info("Consumer starting", extra={"group": self.consumer_group_id})

        try:
            while self._running:
                for message in self._consumer:
                    if not self._running:
                        break
                    self._process_message(message)
        except Exception as exc:
            logger.error(
                "Consumer fatal error", extra={"error": str(exc)}, exc_info=True
            )
            raise
        finally:
            self._consumer.close()
            logger.info("Consumer stopped", extra={"group": self.consumer_group_id})

    def stop(self):
        self._running = False

    # ── Message processing ────────────────────────────────────────────────────

    def _process_message(self, message):
        try:
            event = self.event_class.model_validate_json(message.value)
        except Exception as exc:
            logger.error(
                "Deserialization failed — sending to DLQ",
                extra={
                    "topic": message.topic,
                    "offset": message.offset,
                    "error": str(exc),
                    "raw_value": message.value[:500] if message.value else None,
                },
            )
            self._send_to_dlq(message, exc)
            self._consumer.commit()
            return

        if self._is_duplicate(event):
            logger.debug(
                "Duplicate event skipped",
                extra={"event_id": event.event_id, "event_type": event.event_type},
            )
            self._consumer.commit()
            return

        try:
            self.handle(event)
            self._mark_processed(event)
            self._consumer.commit()
            self._backoff_count = 0  # Reset on success
        except PermanentConsumerError as exc:
            logger.error(
                "Permanent consumer error — sending to DLQ",
                extra={"event_id": event.event_id, "error": str(exc)},
            )
            self._send_to_dlq(message, exc)
            self._consumer.commit()  # Do not block partition
        except TransientConsumerError as exc:
            sleep_time = min(2 ** self._backoff_count, MAX_BACKOFF_SECONDS)
            logger.warning(
                "Transient consumer error — will retry",
                extra={
                    "event_id": event.event_id,
                    "error": str(exc),
                    "backoff_seconds": sleep_time,
                },
            )
            self._backoff_count += 1
            time.sleep(sleep_time)
            # Do NOT commit — message replays on next poll
        except Exception as exc:
            # Unexpected errors treated as permanent
            logger.exception(
                "Unexpected consumer error — sending to DLQ",
                extra={"event_id": event.event_id, "error": str(exc)},
            )
            self._send_to_dlq(message, exc)
            self._consumer.commit()

    @abstractmethod
    def handle(self, event: KafkaEvent) -> None:
        """Process the deserialized, deduplicated event. Implement in subclass."""
        ...

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _dedup_key(self, event: KafkaEvent) -> str:
        return f"kafka:dedup:{self.consumer_group_id}:{event.event_id}"

    def _is_duplicate(self, event: KafkaEvent) -> bool:
        """Return True if this event_id was already processed (within 24h)."""
        key = self._dedup_key(event)
        return self._redis.exists(key) == 1

    def _mark_processed(self, event: KafkaEvent) -> None:
        """Mark event_id as processed in Redis with 24h TTL."""
        key = self._dedup_key(event)
        self._redis.setex(key, 86400, "1")

    # ── DLQ ───────────────────────────────────────────────────────────────────

    def _send_to_dlq(self, message, exc: Exception) -> None:
        if not self.dlq_topic:
            return
        try:
            from sports_platform.kafka.producer import get_producer
            from kafka import KafkaProducer

            producer = KafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            )
            dlq_payload = json.dumps({
                "original_topic": message.topic,
                "original_offset": message.offset,
                "original_partition": message.partition,
                "error": str(exc),
                "raw_value": message.value.decode("utf-8", errors="replace") if message.value else None,
            }).encode("utf-8")
            producer.send(self.dlq_topic, value=dlq_payload)
            producer.flush(timeout=5)
            producer.close()
        except Exception as dlq_exc:
            logger.error(
                "Failed to send to DLQ",
                extra={"dlq_topic": self.dlq_topic, "error": str(dlq_exc)},
            )
