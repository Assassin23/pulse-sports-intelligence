"""
Standings Tool — Milestone 10.

Fetches current competition standings/table.
"""
from typing import Dict, Any, Optional, List
import logging
from sports_platform.sports.models import Competition, CompetitionTeam

logger = logging.getLogger(__name__)


def get_standings(competition_id: Optional[str] = None, match_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch standings for a competition.
    """
    try:
        comp = None
        if competition_id:
            comp = Competition.objects.filter(id=competition_id).first()
        elif match_id:
            from sports_platform.matches.models import Match
            m = Match.objects.select_related("competition").filter(id=match_id).first()
            if m:
                comp = m.competition

        if not comp:
            return {
                "tool": "get_standings",
                "data": [],
                "error": "Competition not specified or not found.",
            }

        # Check if standings are stored in competition metadata
        cached_standings = comp.metadata.get("standings") if hasattr(comp, "metadata") and comp.metadata else None
        if cached_standings:
            return {
                "tool": "get_standings",
                "data": cached_standings,
                "error": None,
            }

        # Query teams participating in competition
        comp_teams = (
            CompetitionTeam.objects.filter(competition=comp)
            .select_related("team")
            .order_by("team__name")[:20]
        )

        table: List[Dict[str, Any]] = []
        for i, ct in enumerate(comp_teams, start=1):
            table.append(
                {
                    "position": i,
                    "team": ct.team.name,
                    "team_id": str(ct.team.id),
                    "played": 0,
                    "points": 0,
                }
            )

        return {
            "tool": "get_standings",
            "data": {
                "competition": comp.name,
                "table": table,
            },
            "error": None,
        }
    except Exception as exc:
        logger.error(f"Error fetching standings: {exc}", exc_info=True)
        return {
            "tool": "get_standings",
            "data": [],
            "error": str(exc),
        }
