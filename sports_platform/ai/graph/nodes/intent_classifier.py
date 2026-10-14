"""
Intent Classifier Node — Milestone 10.
"""
from typing import Dict, Any
import json
import logging
from sports_platform.ai.graph.state import AssistantState
from sports_platform.ai.llm import get_llm
from sports_platform.matches.models import Match

logger = logging.getLogger(__name__)

INTENT_CLASSIFICATION_PROMPT = """
You are a sports domain intent classifier. Classify the user question into exactly one intent:
- "live_update": Current score, live events, match state, who is winning
- "analysis": Tactical assessment, team performance, comparisons
- "context": History, tournament rules, player profiles, terminology
- "prediction": Asking for match outcomes (note: we respond with data, not betting advice)
- "mixed": Requires both live score/events and rules/historical context

Match Context:
- Sport: {sport}
- Teams: {home_team} vs {away_team}
- Current Status: {match_status}

User Question: {question}

Return JSON strictly in this format:
{{
    "intent": "live_update|analysis|context|prediction|mixed",
    "needs_live_score": true/false,
    "needs_match_events": true/false,
    "needs_team_stats": true/false,
    "needs_standings": true/false,
    "needs_recent_matches": true/false,
    "needs_rag_context": true/false
}}
"""


def _get_match_metadata(match_id: str) -> Dict[str, str]:
    try:
        m = Match.objects.select_related("sport", "home_team", "away_team").filter(id=match_id).first()
        if m:
            return {
                "sport": m.sport.name,
                "home_team": m.home_team.name,
                "away_team": m.away_team.name,
                "match_status": m.status,
            }
    except Exception as e:
        logger.warning(f"Failed to fetch match metadata for {match_id}: {e}")

    return {
        "sport": "Sports",
        "home_team": "Home Team",
        "away_team": "Away Team",
        "match_status": "in_progress",
    }


def classify_intent(state: AssistantState) -> Dict[str, Any]:
    """
    Analyzes user question in the context of the active match.
    Identifies primary intent and required backend tools / RAG context.
    """
    match_meta = _get_match_metadata(state["match_id"])
    llm = get_llm()

    prompt = INTENT_CLASSIFICATION_PROMPT.format(
        sport=match_meta["sport"],
        home_team=match_meta["home_team"],
        away_team=match_meta["away_team"],
        match_status=match_meta["match_status"],
        question=state["user_question"],
    )

    try:
        resp = llm.invoke(prompt)
        text = resp.content.strip()
        # Extract json block if wrapped in markdown code fence
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        classification = json.loads(text)
    except Exception as e:
        logger.warning(f"Error parsing intent classification ({e}). Using heuristic fallback.")
        q_lower = state["user_question"].lower()
        is_live = any(k in q_lower for k in ["score", "who is winning", "goal", "wicket", "current", "lead"])
        classification = {
            "intent": "live_update" if is_live else "context",
            "needs_live_score": is_live,
            "needs_match_events": any(k in q_lower for k in ["event", "card", "red card", "substitution"]),
            "needs_team_stats": any(k in q_lower for k in ["stat", "possession", "shots"]),
            "needs_standings": any(k in q_lower for k in ["standing", "table", "points"]),
            "needs_recent_matches": any(k in q_lower for k in ["recent", "last", "h2h"]),
            "needs_rag_context": not is_live or "rule" in q_lower or "history" in q_lower,
        }

    required_tools = []
    if classification.get("needs_live_score"):
        required_tools.append("get_live_score")
    if classification.get("needs_match_events"):
        required_tools.append("get_match_events")
    if classification.get("needs_team_stats"):
        required_tools.append("get_team_stats")
    if classification.get("needs_standings"):
        required_tools.append("get_standings")
    if classification.get("needs_recent_matches"):
        required_tools.append("get_recent_matches")

    needs_rag = bool(classification.get("needs_rag_context"))
    # If no backend tools requested and no RAG, default to live score
    if not required_tools and not needs_rag:
        required_tools.append("get_live_score")

    return {
        "intent": classification.get("intent", "live_update"),
        "required_tools": required_tools,
        "needs_rag": needs_rag,
    }
