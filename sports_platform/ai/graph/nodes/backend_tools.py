"""
Backend Tools Node — Milestone 10.

Executes deterministic backend tools (get_live_score, get_match_events, get_team_stats, etc.)
with structured error handling.
"""
from typing import Dict, Any, List
import logging
from sports_platform.ai.graph.state import AssistantState
from sports_platform.ai.tools import (
    get_live_score,
    get_match_events,
    get_team_stats,
    get_standings,
    get_recent_matches,
)

logger = logging.getLogger(__name__)


def execute_backend_tools(state: AssistantState) -> Dict[str, Any]:
    """
    Executes all scheduled backend tools for this turn.
    Returns accumulated tool_results list.
    """
    match_id = state["match_id"]
    tools_to_run = state.get("required_tools", [])
    results: List[Dict[str, Any]] = []

    for tool_name in tools_to_run:
        try:
            if tool_name == "get_live_score":
                res = get_live_score(match_id)
            elif tool_name == "get_match_events":
                res = get_match_events(match_id, last_n=20)
            elif tool_name == "get_team_stats":
                res = get_team_stats(match_id)
            elif tool_name == "get_standings":
                res = get_standings(match_id=match_id)
            elif tool_name == "get_recent_matches":
                # Find match to get teams
                from sports_platform.matches.models import Match
                m = Match.objects.filter(id=match_id).first()
                if m:
                    res = get_recent_matches(home_team_id=str(m.home_team_id), away_team_id=str(m.away_team_id))
                else:
                    res = {"tool": "get_recent_matches", "data": [], "error": "Match not found."}
            else:
                res = {"tool": tool_name, "data": None, "error": f"Unknown tool '{tool_name}'"}
            results.append(res)
        except Exception as exc:
            logger.error(f"Error executing tool '{tool_name}': {exc}", exc_info=True)
            results.append({"tool": tool_name, "data": None, "error": str(exc)})

    return {"tool_results": results}
