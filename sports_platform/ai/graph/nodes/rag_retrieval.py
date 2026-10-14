"""
RAG Retrieval Node — Milestone 10.

Retrieves contextual knowledge chunks (rules, biographies, team history) from pgvector.
"""
from typing import Dict, Any, List
import logging
from sports_platform.ai.graph.state import AssistantState
from sports_platform.ai.tools.search_knowledge_base import search_knowledge_base
from sports_platform.matches.models import Match

logger = logging.getLogger(__name__)


def retrieve_rag_context(state: AssistantState) -> Dict[str, Any]:
    """
    Queries the RAG knowledge base for background facts, rules, or player profiles.
    """
    match_id = state["match_id"]
    query = state["user_question"]

    sport_slug = None
    try:
        m = Match.objects.select_related("sport").filter(id=match_id).first()
        if m and m.sport:
            sport_slug = m.sport.slug
    except Exception as e:
        logger.warning(f"Could not resolve sport for match {match_id}: {e}")

    result = search_knowledge_base(query=query, sport=sport_slug, top_n=5)
    chunks: List[Dict[str, Any]] = result.get("data", [])

    sources = []
    for c in chunks:
        if "citation" in c:
            sources.append(c["citation"])

    return {
        "rag_chunks": chunks,
        "sources": sources,
    }
