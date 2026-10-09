"""
Redis store for user feed caching and followed match indexing.

Implements the key schema from docs/data-model/05-redis-design.md:
  feed:{user_id}           → String (serialized feed JSON, TTL 5 min)
  feed:{user_id}:{status}  → String (status-filtered feed cache, TTL 5 min)
  user:matches:{user_id}   → Set (user's followed match UUIDs, TTL 10 min)
"""
import json
import logging
from typing import Any, Dict, List, Optional

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

FEED_CACHE_TTL = 300       # 5 minutes
USER_MATCHES_TTL = 600     # 10 minutes


class FeedRedisStore:
    """
    Manages personalized feed caching and fast invalidation in Redis.
    """

    def __init__(self):
        self._redis = redis.Redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )

    @staticmethod
    def feed_key(user_id: str, status_filter: Optional[str] = None) -> str:
        if status_filter:
            return f"feed:{user_id}:{status_filter}"
        return f"feed:{user_id}"

    @staticmethod
    def user_matches_key(user_id: str) -> str:
        return f"user:matches:{user_id}"

    def cache_feed(
        self,
        user_id: str,
        feed_data: Dict[str, Any],
        ttl: int = FEED_CACHE_TTL,
        status_filter: Optional[str] = None,
    ) -> None:
        """Cache the serialized feed payload for a user."""
        key = self.feed_key(user_id, status_filter)
        try:
            self._redis.setex(key, ttl, json.dumps(feed_data))
            logger.debug("Feed cached in Redis", extra={"key": key, "user_id": user_id})
        except Exception as exc:
            logger.warning("Failed to cache feed in Redis", extra={"error": str(exc), "user_id": user_id})

    def get_feed(self, user_id: str, status_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve cached feed JSON if present, else None."""
        key = self.feed_key(user_id, status_filter)
        try:
            data = self._redis.get(key)
            if data:
                return json.loads(data)
        except Exception as exc:
            logger.warning("Failed to read feed from Redis cache", extra={"error": str(exc), "user_id": user_id})
        return None

    def invalidate_feed(self, user_id: str) -> None:
        """
        Invalidate all feed cache entries for the user.
        Deletes feed:{user_id} and any subkeys like feed:{user_id}:live.
        """
        try:
            primary_key = f"feed:{user_id}"
            keys = [primary_key]
            # Match any status-specific feed keys
            pattern = f"feed:{user_id}:*"
            extra_keys = self._redis.keys(pattern)
            if extra_keys:
                keys.extend(extra_keys)
            self._redis.delete(*keys)
            logger.info("Feed cache invalidated", extra={"user_id": user_id, "keys_deleted": len(keys)})
        except Exception as exc:
            logger.warning("Failed to invalidate feed cache in Redis", extra={"error": str(exc), "user_id": user_id})

    def cache_user_matches(self, user_id: str, match_ids: List[str], ttl: int = USER_MATCHES_TTL) -> None:
        """Cache the set of match IDs relevant to the user for fast subscription check."""
        if not match_ids:
            return
        key = self.user_matches_key(user_id)
        try:
            pipe = self._redis.pipeline()
            pipe.delete(key)
            pipe.sadd(key, *match_ids)
            pipe.expire(key, ttl)
            pipe.execute()
        except Exception as exc:
            logger.warning("Failed to cache user matches in Redis", extra={"error": str(exc), "user_id": user_id})

    def get_user_matches(self, user_id: str) -> List[str]:
        """Return cached set of followed match IDs for user."""
        key = self.user_matches_key(user_id)
        try:
            return list(self._redis.smembers(key))
        except Exception as exc:
            logger.warning("Failed to get user matches from Redis", extra={"error": str(exc), "user_id": user_id})
            return []


# ── Singleton ─────────────────────────────────────────────────────────────────

_feed_store: Optional[FeedRedisStore] = None


def get_feed_store() -> FeedRedisStore:
    global _feed_store
    if _feed_store is None:
        _feed_store = FeedRedisStore()
    return _feed_store
