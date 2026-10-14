"""
Live Score Tool — Milestone 10.

Fetches current live score from Redis (authoritative) with fallback to PostgreSQL.
Returns structured dictionary, avoiding exceptions.
"""
from typing import Dict, Any, Optional
import logging
from sports_platform.matches.models import Match, MatchScore

logger = logging.getLogger(__name__)


def get_live_score(match_id: str) -> Dict[str, Any]:
    """
    Fetch current score for a match.
    First checks Redis, then falls back to PostgreSQL.
    """
    try:
        from sports_platform.matches.redis_store import MatchRedisStore
        redis_store = MatchRedisStore()
        score_cache = redis_store.get_score(match_id)
        if score_cache:
            return {
                "tool": "get_live_score",
                "data": {
                    "match_id": match_id,
                    "source": "redis_live",
                    "status": score_cache.get("status"),
                    "score_data": score_cache.get("score_data"),
                    "sequence_number": score_cache.get("sequence_number"),
                },
                "error": None,
            }
    except Exception as e:
        logger.warning(f"Failed to read live score from Redis for match {match_id}: {e}")

    # Database fallback
    try:
        score_obj = MatchScore.objects.select_related("match", "match__home_team", "match__away_team").filter(match_id=match_id).first()
        if score_obj:
            return {
                "tool": "get_live_score",
                "data": {
                    "match_id": match_id,
                    "source": "postgres_durable",
                    "status": score_obj.match.status,
                    "home_team": score_obj.match.home_team.name,
                    "away_team": score_obj.match.away_team.name,
                    "score_data": score_obj.score_data,
                    "sequence_number": score_obj.sequence_number,
                },
                "error": None,
            }

        # Check if match exists without score record
        match = Match.objects.select_related("home_team", "away_team").filter(id=match_id).first()
        if match:
            return {
                "tool": "get_live_score",
                "data": {
                    "match_id": match_id,
                    "source": "postgres_match",
                    "status": match.status,
                    "home_team": match.home_team.name,
                    "away_team": match.away_team.name,
                    "score_data": {},
                    "sequence_number": 0,
                },
                "error": None,
            }

        return {
            "tool": "get_live_score",
            "data": None,
            "error": f"Match with id '{match_id}' not found.",
        }
    except Exception as exc:
        logger.error(f"Error fetching live score for match {match_id}: {exc}", exc_info=True)
        return {
            "tool": "get_live_score",
            "data": None,
            "error": str(exc),
        }
