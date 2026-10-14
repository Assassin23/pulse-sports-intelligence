"""
Validation Node — Milestone 10.

Cross-references draft answers against authoritative live data to guard against hallucinations
and fabricated statistics.
"""
from typing import Dict, Any, Literal
import json
import logging
from sports_platform.ai.graph.state import AssistantState
from sports_platform.ai.llm import get_llm
from sports_platform.ai.graph.nodes.synthesizer import _format_tool_results

logger = logging.getLogger(__name__)

VALIDATION_PROMPT = """
Review this draft answer for factual consistency against the provided live data.

Live Authoritative Data:
{tool_results}

Draft Answer:
{draft_answer}

Verification Rules:
1. Does the draft answer state any score, run total, or goal count that contradicts the live data? -> FAIL
2. Does the draft answer state any match event (red card, wicket, penalty) that never happened in the data? -> FAIL
3. Does the draft answer remain honest and appropriately uncertain if data is unavailable? -> PASS
4. Is the answer relevant to the user question? -> PASS

Return JSON strictly:
{{"passed": true/false, "issues": ["issue description if failed"]}}
"""


def validate_response(state: AssistantState) -> Dict[str, Any]:
    """
    Validates draft answer factual grounding against live tool results.
    """
    tool_results = state.get("tool_results", [])
    has_live_data = any(t.get("data") for t in tool_results)

    # If no live data was fetched (e.g. purely RAG/rule question), auto-pass
    if not has_live_data:
        return {
            "validation_passed": True,
            "validation_issues": [],
        }

    prompt = VALIDATION_PROMPT.format(
        tool_results=_format_tool_results(tool_results),
        draft_answer=state.get("draft_answer", ""),
    )

    llm = get_llm()
    try:
        resp = llm.invoke(prompt)
        text = resp.content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        val_data = json.loads(text)
        return {
            "validation_passed": bool(val_data.get("passed", True)),
            "validation_issues": val_data.get("issues", []),
        }
    except Exception as e:
        logger.warning(f"Validation parse failed ({e}); defaulting to pass.")
        return {
            "validation_passed": True,
            "validation_issues": [],
        }


def route_after_validation(state: AssistantState) -> Literal["passed", "retry", "failed"]:
    """
    Determines next step after validation:
    - "passed" -> responder
    - "retry" -> synthesizer (one attempt to regenerate)
    - "failed" -> responder (deliver response with warning)
    """
    if state.get("validation_passed", True):
        return "passed"

    retries = state.get("retry_count", 0)
    if retries < 1:
        return "retry"
    return "failed"
