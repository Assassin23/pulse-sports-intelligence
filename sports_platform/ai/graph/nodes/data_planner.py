"""
Data Planning Node — Milestone 10.
"""
from typing import Dict, Any, Literal
from sports_platform.ai.graph.state import AssistantState


def plan_data_requirements(state: AssistantState) -> Dict[str, Any]:
    """
    Validates data requirements formulated by the Intent Classifier.
    """
    return {}


def route_after_planning(state: AssistantState) -> Literal["tools_only", "rag_only", "both"]:
    """
    Determines execution branch:
    - "tools_only": live scores/events only
    - "rag_only": rules/knowledge search only
    - "both": parallel execution of backend tools and RAG retrieval
    """
    has_tools = bool(state.get("required_tools"))
    has_rag = bool(state.get("needs_rag"))

    if has_tools and has_rag:
        return "both"
    elif has_rag:
        return "rag_only"
    return "tools_only"
