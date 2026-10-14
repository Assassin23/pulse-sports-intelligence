"""
LLM Client Interface and Factory — Milestone 10.

Pluggable interface for language model invocation.
Provides OpenAIChatClient for production and MockChatClient for deterministic offline testing.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import json
import re
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    usage_metadata: Dict[str, int] = field(default_factory=lambda: {"input_tokens": 100, "output_tokens": 80})


class BaseLLMClient:
    async def ainvoke(self, prompt: str) -> LLMResponse:
        return self.invoke(prompt)

    def invoke(self, prompt: str) -> LLMResponse:
        raise NotImplementedError


class OpenAIChatClient(BaseLLMClient):
    """Production OpenAI chat client."""

    def __init__(self, api_key: str, model: Optional[str] = None):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self.model = model or getattr(settings, "OPENAI_CHAT_MODEL", "gpt-4o-mini")

    def invoke(self, prompt: str) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            choice = response.choices[0]
            usage = {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            }
            return LLMResponse(content=choice.message.content or "", usage_metadata=usage)
        except Exception as e:
            logger.error(f"OpenAI chat completion error: {e}")
            raise


class MockChatClient(BaseLLMClient):
    """
    Deterministic mock chat client for offline development and test suites.
    Simulates intent classification, synthesis, and response validation.
    """

    def invoke(self, prompt: str) -> LLMResponse:
        lower = prompt.lower()

        # 1. Intent Classification Prompt
        if "classify the primary intent" in lower or "needs_live_score" in lower:
            # Check question keywords
            needs_live_score = any(k in lower for k in ["score", "current", "winning", "lead", "runs", "goals"])
            needs_match_events = any(k in lower for k in ["event", "goal", "wicket", "card", "happen", "minute", "red card"])
            needs_team_stats = any(k in lower for k in ["stat", "possession", "shots", "fouls", "run rate"])
            needs_standings = any(k in lower for k in ["table", "standing", "points", "rank", "position"])
            needs_recent_matches = any(k in lower for k in ["recent", "last match", "head to head", "h2h", "form"])
            needs_rag_context = any(k in lower for k in ["rule", "history", "profile", "career", "format", "tiebreak", "offside", "drs"])

            intent = "live_update" if needs_live_score or needs_match_events else "context"
            if needs_rag_context and (needs_live_score or needs_team_stats):
                intent = "mixed"
            elif needs_rag_context:
                intent = "context"

            classification = {
                "intent": intent,
                "needs_live_score": needs_live_score or intent == "live_update",
                "needs_match_events": needs_match_events,
                "needs_team_stats": needs_team_stats,
                "needs_standings": needs_standings,
                "needs_recent_matches": needs_recent_matches,
                "needs_rag_context": needs_rag_context or intent in ["context", "mixed"],
            }
            return LLMResponse(content=json.dumps(classification))

        # 2. Validation Prompt
        if "review this answer for factual consistency" in lower or "flag as fail" in lower:
            # Deterministic validation response
            validation = {
                "passed": True,
                "issues": [],
            }
            return LLMResponse(content=json.dumps(validation))

        # 3. Synthesis Prompt
        if "live data from tools" in lower or "background context" in lower:
            # Extract question if present
            question_match = re.search(r"User Question:\s*(.+)", prompt)
            user_q = question_match.group(1).strip() if question_match else "your match question"

            answer_parts = [
                f"Based on the official match data for {user_q}:",
            ]

            # Look for live score in prompt
            if "score_data" in prompt or "score:" in lower:
                answer_parts.append("The current match score and state have been updated according to real-time provider data.")

            # Look for events
            if "match_events" in lower or "goal" in lower or "wicket" in lower:
                answer_parts.append("Recent key match events and milestones have been registered chronologically.")

            # Look for background context
            if "background context" in lower:
                answer_parts.append("According to the tournament rules and team history in the knowledge base, tactical preparation and disciplinary rules are strictly governed.")

            answer_parts.append("Is there anything specific about this fixture or the players you would like to analyze further?")

            return LLMResponse(
                content="\n\n".join(answer_parts),
                usage_metadata={"input_tokens": 150, "output_tokens": 90},
            )

        # Default conversational response
        return LLMResponse(
            content="Here is the sports intelligence analysis based on live authoritative data and reference rules.",
            usage_metadata={"input_tokens": 80, "output_tokens": 50},
        )


def get_llm(api_key: Optional[str] = None) -> BaseLLMClient:
    """Return configured LLM client instance."""
    key = api_key or getattr(settings, "OPENAI_API_KEY", "")
    if key and key.strip() and not key.startswith("your-") and not key.startswith("<"):
        try:
            return OpenAIChatClient(api_key=key.strip())
        except Exception as e:
            logger.warning(f"Could not initialize OpenAIChatClient ({e}). Using MockChatClient.")

    logger.info("Using MockChatClient for AI assistant (deterministic local mode).")
    return MockChatClient()
