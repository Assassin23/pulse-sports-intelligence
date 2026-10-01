"""
Redis state manager for live match data.

Implements the Redis key schema defined in docs/data-model/05-redis-design.md.

Key schema:
  match:score:{match_id}        → Hash  (current score)
  match:meta:{match_id}         → Hash  (match metadata cache)
  match:events:recent:{match_id}→ ZSet  (last 50 events, scored by event_sequence)
  matches:live                  → Set   (live match UUIDs)
  matches:upcoming:{sport_slug} → ZSet  (upcoming match IDs, scored by scheduled_at unix)
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis

from django.conf import settings

logger = logging.getLogger(__name__)

# Max recent events kept in Redis per match
RECENT_EVENTS_LIMIT = 50

# TTLs (seconds)
SCORE_TTL = 86400       # 24h from last update
SCORE_TTL_POST_MATCH = 21600  # 6h after completion
META_TTL = 7200         # 2h
EVENTS_TTL = 86400      # 24h
UPCOMING_TTL = 3600     # 1h


class MatchRedisStore:
    """
    Encapsulates all Redis operations for live match state.

    Uses a dedicated redis client (not Django's cache layer)
    for pipeline/atomic operations and fine-grained TTL control.
    """

    def __init__(self):
        self._redis = redis.Redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )

    # ── Key builders ──────────────────────────────────────────────────────────

    @staticmethod
    def score_key(match_id: str) -> str:
        return f"match:score:{match_id}"

    @staticmethod
    def meta_key(match_id: str) -> str:
        return f"match:meta:{match_id}"

    @staticmethod
    def events_key(match_id: str) -> str:
        return f"match:events:recent:{match_id}"

    @staticmethod
    def live_set_key() -> str:
        return "matches:live"

    @staticmethod
    def upcoming_key(sport_slug: str) -> str:
        return f"matches:upcoming:{sport_slug}"

    # ── Score operations ──────────────────────────────────────────────────────

    def update_score(
        self,
        match_id: str,
        score_data: Dict[str, Any],
        sequence_number: int,
        status: str,
    ) -> None:
        """
        Idempotent score update with sequence guard.
        Uses Lua script to atomically check sequence before writing.
        """
        key = self.score_key(match_id)

        # Lua script: only update if new sequence_number > existing
        lua_script = """
        local key = KEYS[1]
        local new_seq = tonumber(ARGV[1])
        local existing_seq = tonumber(redis.call('HGET', key, 'sequence_number') or -1)
        if new_seq <= existing_seq then
            return 0
        end
        redis.call('HSET', key,
            'score_data', ARGV[2],
            'sequence_number', ARGV[1],
            'status', ARGV[3],
            'updated_at', ARGV[4]
        )
        redis.call('EXPIRE', key, ARGV[5])
        return 1
        """
        result = self._redis.eval(
            lua_script,
            1,
            key,
            str(sequence_number),
            json.dumps(score_data),
            status,
            str(int(time.time())),
            str(SCORE_TTL),
        )
        if result == 1:
            logger.debug(
                "Score updated in Redis",
                extra={"match_id": match_id, "sequence": sequence_number},
            )
        else:
            logger.debug(
                "Score update skipped (stale sequence)",
                extra={"match_id": match_id, "sequence": sequence_number},
            )

    def get_score(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Return current score data or None if not cached."""
        data = self._redis.hgetall(self.score_key(match_id))
        if not data:
            return None
        result = dict(data)
        if "score_data" in result:
            result["score_data"] = json.loads(result["score_data"])
        return result

    # ── Match metadata ────────────────────────────────────────────────────────

    def cache_match_meta(self, match_id: str, meta: Dict[str, str]) -> None:
        """Cache match metadata (teams, competition, etc.) for fast API reads."""
        key = self.meta_key(match_id)
        pipe = self._redis.pipeline()
        pipe.hset(key, mapping=meta)
        pipe.expire(key, META_TTL)
        pipe.execute()

    def get_match_meta(self, match_id: str) -> Optional[Dict[str, str]]:
        data = self._redis.hgetall(self.meta_key(match_id))
        return dict(data) if data else None

    # ── Live match tracking ───────────────────────────────────────────────────

    def add_to_live(self, match_id: str) -> None:
        self._redis.sadd(self.live_set_key(), match_id)
        logger.info("Match added to live set", extra={"match_id": match_id})

    def remove_from_live(self, match_id: str) -> None:
        self._redis.srem(self.live_set_key(), match_id)
        logger.info("Match removed from live set", extra={"match_id": match_id})

    def get_live_match_ids(self) -> List[str]:
        return list(self._redis.smembers(self.live_set_key()))

    # ── Recent events ─────────────────────────────────────────────────────────

    def push_event(self, match_id: str, event_sequence: int, event_payload: dict) -> None:
        """
        Add event to recent events sorted set (score = event_sequence).
        Trim to RECENT_EVENTS_LIMIT most recent entries.
        """
        key = self.events_key(match_id)
        pipe = self._redis.pipeline()
        pipe.zadd(key, {json.dumps(event_payload): event_sequence})
        pipe.zremrangebyrank(key, 0, -(RECENT_EVENTS_LIMIT + 1))
        pipe.expire(key, EVENTS_TTL)
        pipe.execute()

    def get_recent_events(self, match_id: str, limit: int = 20) -> List[dict]:
        """Return up to `limit` most recent events for a match."""
        key = self.events_key(match_id)
        raw = self._redis.zrange(key, 0, limit - 1, desc=True)
        events = []
        for item in raw:
            try:
                events.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Malformed event in Redis", extra={"match_id": match_id})
        return events

    # ── Upcoming match index ──────────────────────────────────────────────────

    def add_upcoming(self, sport_slug: str, match_id: str, scheduled_at: datetime) -> None:
        key = self.upcoming_key(sport_slug)
        score = scheduled_at.timestamp()
        pipe = self._redis.pipeline()
        pipe.zadd(key, {match_id: score})
        pipe.expire(key, UPCOMING_TTL)
        pipe.execute()

    def get_upcoming_ids(
        self,
        sport_slug: str,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        limit: int = 20,
    ) -> List[str]:
        key = self.upcoming_key(sport_slug)
        now = time.time()
        min_score = from_ts if from_ts is not None else now
        max_score = to_ts if to_ts is not None else "+inf"
        return list(
            self._redis.zrangebyscore(key, min_score, max_score, start=0, num=limit)
        )

    def rebuild_upcoming(self, sport_slug: str, matches: list) -> None:
        """Bulk rebuild upcoming index from a list of (match_id, scheduled_at) tuples."""
        key = self.upcoming_key(sport_slug)
        pipe = self._redis.pipeline()
        pipe.delete(key)
        for match_id, scheduled_at in matches:
            pipe.zadd(key, {match_id: scheduled_at.timestamp()})
        pipe.expire(key, UPCOMING_TTL)
        pipe.execute()

    # ── Invalidation ─────────────────────────────────────────────────────────

    def expire_score_fast(self, match_id: str) -> None:
        """Shorten TTL to 6h after match completion."""
        self._redis.expire(self.score_key(match_id), SCORE_TTL_POST_MATCH)


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: Optional[MatchRedisStore] = None


def get_match_store() -> MatchRedisStore:
    global _store
    if _store is None:
        _store = MatchRedisStore()
    return _store
