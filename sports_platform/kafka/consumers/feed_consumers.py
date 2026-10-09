"""
Kafka consumers for feed processing (Milestone 5).

FeedInvalidationConsumer:
  Topic:    sports.user.preference.updated
  Action:   Invalidates Redis feed cache (feed:{user_id}) so subsequent requests rebuild from PostgreSQL.
"""
import logging

from sports_platform.feed.services import FeedService
from sports_platform.kafka.base_consumer import BaseKafkaConsumer
from sports_platform.kafka.events import KafkaTopics, UserPreferenceUpdatedEvent

logger = logging.getLogger(__name__)


class FeedInvalidationConsumer(BaseKafkaConsumer):
    """
    Consumes: sports.user.preference.updated
    Action:   Invalidates Redis feed cache for the affected user.
    """

    event_class = UserPreferenceUpdatedEvent
    topics = [KafkaTopics.USER_PREFERENCE_UPDATED]
    consumer_group_id = "feed-invalidation"

    def handle(self, event: UserPreferenceUpdatedEvent) -> None:
        user_id = event.user_id
        FeedService.invalidate_feed_cache(user_id)
        logger.info(
            "Feed cache invalidated by consumer",
            extra={
                "user_id": user_id,
                "change_type": event.change_type,
                "event_id": event.event_id,
            },
        )
