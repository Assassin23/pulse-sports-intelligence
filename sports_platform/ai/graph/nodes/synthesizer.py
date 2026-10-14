"""
Synthesizer Node — Milestone 10.

Prompts the LLM to synthesize an engaging, conversational answer grounded strictly in
deterministic live tool data and authoritative RAG background context.
"""
from typing import Dict, Any, List
import json
import logging
from sports_platform.ai.graph.state import AssistantState
from sports_platform.ai.llm import get_llm
from sports_platform.matches.models import Match

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """
You are an expert, knowledgeable sports assistant. Answer the user's question using ONLY the provided authoritative data.

CRITICAL RULES:
1. Never invent, extrapolate, or assume scores, events, or statistics not present in the live data.
2. If live data or a tool returned an error or empty data, state that clearly without guessing.
3. Use background context exclusively for rules, player histories, tactics, and tournament formats.
4. Keep the tone concise, engaging, and professional. The user is actively following this match.
5. Do not output raw JSON or code unless asked.

Match Context:
- Sport: {sport}
- Teams: {home_team} vs {away_team}
- Current Status: {match_status}

Live Data from Authoritative Tools:
{tool_results_formatted}

Background Reference Knowledge (from RAG):
{rag_context_formatted}

Conversation History:
{conversation_history_formatted}

User Question: {question}

Answer:
"""


def _format_tool_results(tool_results: List[Dict[str, Any]]) -> str:
    if not tool_results:
        return "No backend tools executed."
    formatted = []
    for t in tool_results:
        tool_name = t.get("tool", "tool")
        err = t.get("error")
        if err:
            formatted.append(f"[{tool_name}]: Error: {err}")
        else:
            data = t.get("data")
            formatted.append(f"[{tool_name}]: {json.dumps(data, default=str)}")
    return "\n".join(formatted)


def _format_rag_chunks(rag_chunks: List[Dict[str, Any]]) -> str:
    if not rag_chunks:
        return "No background reference documents retrieved."
    formatted = []
    for i, c in enumerate(rag_chunks, start=1):
        title = c.get("title", f"Document {i}")
        content = c.get("content", "")
        formatted.append(f"Source [{title}]:\n{content}")
    return "\n\n".join(formatted)


def _format_history(history: List[Dict[str, str]]) -> str:
    if not history:
        return "None"
    formatted = []
    for m in history[-5:]:
        role = m.get("role", "user").capitalize()
        content = m.get("content", "")
        formatted.append(f"{role}: {content}")
    return "\n".join(formatted)


def synthesize_answer(state: AssistantState) -> Dict[str, Any]:
    """
    Synthesize draft answer via grounded LLM generation.
    """
    match_id = state["match_id"]
    home_team = "Home Team"
    away_team = "Away Team"
    sport = "Sports"
    match_status = "live"

    try:
        m = Match.objects.select_related("sport", "home_team", "away_team").filter(id=match_id).first()
        if m:
            home_team = m.home_team.name
            away_team = m.away_team.name
            sport = m.sport.name
            match_status = m.status
    except Exception as e:
        logger.warning(f"Error fetching match for synthesizer: {e}")

    prompt = SYNTHESIS_PROMPT.format(
        sport=sport,
        home_team=home_team,
        away_team=away_team,
        match_status=match_status,
        tool_results_formatted=_format_tool_results(state.get("tool_results", [])),
        rag_context_formatted=_format_rag_chunks(state.get("rag_chunks", [])),
        conversation_history_formatted=_format_history(state.get("conversation_history", [])),
        question=state["user_question"],
    )

    llm = get_llm()
    resp = llm.invoke(prompt)

    return {
        "draft_answer": resp.content.strip(),
        "token_usage": resp.usage_metadata,
    }
