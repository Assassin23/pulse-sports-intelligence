"""
Recent Matches Tool — Milestone 10.

Fetches last N matches for a team or head-to-head encounters between two teams.
"""
from typing import Dict, Any, Optional, List
import logging
from django.db.models import Q
from sports_platform.matches.models import Match

logger = logging.getLogger(__name__)


def get_recent_matches(
    team_id: Optional[str] = None,
    home_team_id: Optional[str] = None,
    away_team_id: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Fetch recent matches for team_id, or head-to-head matches between home_team_id and away_team_id.
    """
    try:
        qs = Match.objects.select_related("home_team", "away_team", "competition").order_by("-scheduled_at")

        # Head to head filter
        if home_team_id and away_team_id:
            qs = qs.filter(
                (Q(home_team_id=home_team_id) & Q(away_team_id=away_team_id))
                | (Q(home_team_id=away_team_id) & Q(away_team_id=home_team_id))
            )
        elif team_id:
            qs = qs.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))
        else:
            return {
                "tool": "get_recent_matches",
                "data": [],
                "error": "Must provide team_id or both home_team_id and away_team_id.",
            }

        recent_list: List[Dict[str, Any]] = []
        for m in qs[:limit]:
            recent_list.append(
                {
                    "match_id": str(m.id),
                    "home_team": m.home_team.name,
                    "away_team": m.away_team.name,
                    "competition": m.competition.name,
                    "status": m.status,
                    "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
                }
            )

        return {
            "tool": "get_recent_matches",
            "data": recent_list,
            "error": None,
        }
    except Exception as exc:
        logger.error(f"Error fetching recent matches: {exc}", exc_info=True)
        return {
            "tool": "get_recent_matches",
            "data": [],
            "error": str(exc),
        }
