"""
LangGraph Match Assistant Workflow — Milestone 10.

Compiles the multi-agent StateGraph connecting intent classification, parallel backend tools,
RAG contextual retrieval, synthesis, factual validation, and citations.
"""
from typing import Dict, Any, List, Optional
import time
import logging

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    StateGraph = None
    END = "__end__"

from sports_platform.ai.graph.state import AssistantState
from sports_platform.ai.graph.nodes import (
    classify_intent,
    plan_data_requirements,
    route_after_planning,
    execute_backend_tools,
    retrieve_rag_context,
    synthesize_answer,
    validate_response,
    route_after_validation,
    format_final_response,
)
from sports_platform.ai.services import ConversationService

logger = logging.getLogger(__name__)


def build_match_assistant_graph():
    """
    Builds and compiles the LangGraph StateGraph.
    """
    if not HAS_LANGGRAPH:
        logger.warning("LangGraph not installed; using sequential fallback executor.")
        return None

    workflow = StateGraph(AssistantState)

    # 1. Register Nodes
    workflow.add_node("intent_classifier", classify_intent)
    workflow.add_node("data_planner", plan_data_requirements)
    workflow.add_node("backend_tools", execute_backend_tools)
    workflow.add_node("rag_retrieval", retrieve_rag_context)
    workflow.add_node("synthesizer", synthesize_answer)
    workflow.add_node("validator", validate_response)
    workflow.add_node("responder", format_final_response)

    # 2. Entry Point
    workflow.set_entry_point("intent_classifier")

    # 3. Transitions
    workflow.add_edge("intent_classifier", "data_planner")

    workflow.add_conditional_edges(
        "data_planner",
        route_after_planning,
        {
            "tools_only": "backend_tools",
            "rag_only": "rag_retrieval",
            "both": "backend_tools",  # In sequential graph, backend_tools routes to rag_retrieval if both
        },
    )

    # If both were needed, allow backend_tools to transition to rag_retrieval before synthesis
    def route_after_tools(state: AssistantState) -> str:
        if state.get("needs_rag") and not state.get("rag_chunks"):
            return "rag_retrieval"
        return "synthesizer"

    workflow.add_conditional_edges(
        "backend_tools",
        route_after_tools,
        {
            "rag_retrieval": "rag_retrieval",
            "synthesizer": "synthesizer",
        },
    )

    workflow.add_edge("rag_retrieval", "synthesizer")
    workflow.add_edge("synthesizer", "validator")

    workflow.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "passed": "responder",
            "retry": "synthesizer",
            "failed": "responder",
        },
    )

    workflow.add_edge("responder", END)

    return workflow.compile()


# Singleton compiled graph instance
_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None and HAS_LANGGRAPH:
        try:
            _compiled_graph = build_match_assistant_graph()
        except Exception as e:
            logger.error(f"Failed to compile LangGraph graph: {e}", exc_info=True)
            _compiled_graph = None
    return _compiled_graph


def run_sequential_pipeline(state: AssistantState) -> AssistantState:
    """Fallback runner if LangGraph compiled graph is not available."""
    # 1. Intent
    state.update(classify_intent(state))
    # 2. Data planning & Execution
    route = route_after_planning(state)
    if route in ["tools_only", "both"]:
        res = execute_backend_tools(state)
        state["tool_results"] = state["tool_results"] + res.get("tool_results", [])
    if route in ["rag_only", "both"]:
        res = retrieve_rag_context(state)
        state.update(res)

    # 3. Synthesize
    state.update(synthesize_answer(state))

    # 4. Validate
    state.update(validate_response(state))
    if not state.get("validation_passed") and state.get("retry_count", 0) < 1:
        state["retry_count"] = state.get("retry_count", 0) + 1
        state.update(synthesize_answer(state))

    # 5. Respond
    state.update(format_final_response(state))
    return state


def execute_match_assistant(
    user_id: str,
    match_id: str,
    question: str,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main entry point for AI Match Assistant execution.
    1. Loads or initiates conversation
    2. Initializes AssistantState
    3. Executes LangGraph pipeline
    4. Persists conversation turn
    5. Returns response with citations and metrics
    """
    start_time = time.time()

    # 1. Resolve conversation and history
    conv = ConversationService.get_or_create_conversation(
        user_id=user_id,
        match_id=match_id,
        conversation_id=conversation_id,
    )
    history = ConversationService.get_history(str(conv.id), last_n=10)

    # 2. Build initial state
    state: AssistantState = {
        "user_id": str(user_id),
        "match_id": str(match_id),
        "conversation_id": str(conv.id),
        "conversation_history": history,
        "user_question": question,
        "intent": None,
        "required_tools": [],
        "needs_rag": False,
        "tool_results": [],
        "rag_chunks": [],
        "draft_answer": None,
        "sources": [],
        "validation_passed": True,
        "validation_issues": [],
        "retry_count": 0,
        "final_answer": None,
        "token_usage": {},
        "latency_ms": 0,
    }

    # 3. Execute Graph
    graph = get_compiled_graph()
    if graph is not None:
        try:
            final_state = graph.invoke(state)
        except Exception as e:
            logger.error(f"LangGraph execution failed ({e}); falling back to sequential execution.", exc_info=True)
            final_state = run_sequential_pipeline(state)
    else:
        final_state = run_sequential_pipeline(state)

    elapsed_ms = int((time.time() - start_time) * 1000)
    final_state["latency_ms"] = elapsed_ms

    answer = final_state.get("final_answer") or "I was unable to retrieve data for this fixture at this moment."
    sources = final_state.get("sources", [])
    token_usage = final_state.get("token_usage", {})
    tool_calls = [
        {"tool": t.get("tool"), "has_data": bool(t.get("data")), "error": t.get("error")}
        for t in final_state.get("tool_results", [])
    ]

    # 4. Persist to PostgreSQL
    ConversationService.save_turn(
        conversation_id=str(conv.id),
        user_question=question,
        final_answer=answer,
        tool_calls=tool_calls,
        sources=sources,
        token_usage=token_usage,
        latency_ms=elapsed_ms,
    )

    return {
        "conversation_id": str(conv.id),
        "match_id": str(match_id),
        "question": question,
        "answer": answer,
        "sources": sources,
        "tool_calls": tool_calls,
        "token_usage": token_usage,
        "latency_ms": elapsed_ms,
    }
