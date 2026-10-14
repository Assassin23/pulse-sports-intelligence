"""
Team Stats Tool — Milestone 10.

Computes and returns match statistics (shots, corners, fouls, possession, wickets, runs).
Derived from match metadata, score snapshots, and event aggregations.
"""
from typing import Dict, Any, Optional
import logging
from django.db.models import Count, Q

from sports_platform.matches.models import Match, MatchEvent

logger = logging.getLogger(__name__)


def get_team_stats(match_id: str, team_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch or aggregate match statistics for a match and optionally a specific team.
    """
    try:
        match = (
            Match.objects.select_related("home_team", "away_team", "sport")
            .filter(id=match_id)
            .first()
        )
        if not match:
            return {
                "tool": "get_team_stats",
                "data": None,
                "error": f"Match with id '{match_id}' not found.",
            }

        # Check if match has pre-calculated stats in metadata
        stats_meta = match.metadata.get("statistics") or match.metadata.get("stats")
        if stats_meta:
            return {
                "tool": "get_team_stats",
                "data": stats_meta,
                "error": None,
            }

        # Aggregate from match events
        events_qs = MatchEvent.objects.filter(match_id=match_id)
        home_events = events_qs.filter(team=match.home_team)
        away_events = events_qs.filter(team=match.away_team)

        home_goals = home_events.filter(event_type__in=["goal", "penalty_goal"]).count()
        away_goals = away_events.filter(event_type__in=["goal", "penalty_goal"]).count()

        home_cards = home_events.filter(event_type__in=["yellow_card", "red_card"]).count()
        away_cards = away_events.filter(event_type__in=["yellow_card", "red_card"]).count()

        computed_stats = {
            "match_id": str(match.id),
            "sport": match.sport.slug,
            "home_team": {
                "id": str(match.home_team.id),
                "name": match.home_team.name,
                "goals": home_goals,
                "cards": home_cards,
                "total_events": home_events.count(),
            },
            "away_team": {
                "id": str(match.away_team.id),
                "name": match.away_team.name,
                "goals": away_goals,
                "cards": away_cards,
                "total_events": away_events.count(),
            },
        }

        return {
            "tool": "get_team_stats",
            "data": computed_stats,
            "error": None,
        }
    except Exception as exc:
        logger.error(f"Error computing team stats for match {match_id}: {exc}", exc_info=True)
        return {
            "tool": "get_team_stats",
            "data": None,
            "error": str(exc),
        }
