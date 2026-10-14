"""
LangGraph Assistant State — Milestone 10.

Defines the shared state dictionary accumulated across all graph execution nodes.
"""
from typing import Annotated, List, Optional, TypedDict, Dict, Any
import operator


class AssistantState(TypedDict):
    # Context
    user_id: str
    match_id: str
    conversation_id: str
    conversation_history: List[Dict[str, str]]

    # Current turn
    user_question: str
    intent: Optional[str]  # 'live_update', 'analysis', 'context', 'prediction', 'mixed'
    required_tools: List[str]
    needs_rag: bool

    # Accumulated tool outputs (merged across parallel nodes)
    tool_results: Annotated[List[Dict[str, Any]], operator.add]

    # RAG results
    rag_chunks: List[Dict[str, Any]]

    # Synthesis & Sources
    draft_answer: Optional[str]
    sources: List[Dict[str, Any]]

    # Validation & Routing
    validation_passed: bool
    validation_issues: List[str]
    retry_count: int

    # Final Response
    final_answer: Optional[str]
    token_usage: Optional[Dict[str, int]]
    latency_ms: Optional[int]
