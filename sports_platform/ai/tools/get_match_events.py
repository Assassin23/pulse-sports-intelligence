"""
Match Events Tool — Milestone 10.

Fetches chronological match events (goals, wickets, cards, fouls, substitutions).
Checks Redis recent events sorted set, with durable fallback to PostgreSQL.
"""
from typing import Dict, Any, List
import logging
from sports_platform.matches.models import MatchEvent

logger = logging.getLogger(__name__)


def get_match_events(match_id: str, last_n: int = 20) -> Dict[str, Any]:
    """
    Fetch up to last_n chronological events for a match.
    """
    events_data: List[Dict[str, Any]] = []

    # 1. Try Redis cache
    try:
        from sports_platform.matches.redis_store import MatchRedisStore
        redis_store = MatchRedisStore()
        cached_events = redis_store.get_recent_events(match_id, limit=last_n)
        if cached_events:
            return {
                "tool": "get_match_events",
                "data": cached_events[:last_n],
                "error": None,
            }
    except Exception as e:
        logger.warning(f"Failed to read events from Redis for match {match_id}: {e}")

    # 2. Database fallback
    try:
        qs = (
            MatchEvent.objects.filter(match_id=match_id)
            .select_related("player", "team")
            .order_by("-event_sequence")[:last_n]
        )
        for ev in reversed(list(qs)):
            events_data.append(
                {
                    "event_type": ev.event_type,
                    "event_sequence": ev.event_sequence,
                    "minute": ev.minute,
                    "over_ball": ev.over_ball,
                    "player": ev.player.name if ev.player else None,
                    "team": ev.team.name if ev.team else None,
                    "description": ev.description,
                    "event_data": ev.event_data,
                }
            )

        return {
            "tool": "get_match_events",
            "data": events_data,
            "error": None,
        }
    except Exception as exc:
        logger.error(f"Error fetching match events for {match_id}: {exc}", exc_info=True)
        return {
            "tool": "get_match_events",
            "data": [],
            "error": str(exc),
        }
