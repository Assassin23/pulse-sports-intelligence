"""
Responder Node — Milestone 10.

Formats the final answer, attaches citations, and prepares delivery payloads.
"""
from typing import Dict, Any
from sports_platform.ai.graph.state import AssistantState


def format_final_response(state: AssistantState) -> Dict[str, Any]:
    """
    Finalizes response string, including citations and warning disclaimers if validation failed.
    """
    draft = state.get("draft_answer", "Information is currently unavailable.")
    passed = state.get("validation_passed", True)
    issues = state.get("validation_issues", [])

    final_answer = draft
    if not passed and issues:
        warning_note = f"\n\n*(Note: Some live details could not be fully verified against official records: {', '.join(issues)})*"
        final_answer = draft + warning_note

    return {
        "final_answer": final_answer,
    }
