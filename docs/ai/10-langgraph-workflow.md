# 10. LangGraph AI Match Assistant

## 10.1 Graph Overview

```
User Question
      │
      ▼
┌─────────────────┐
│ Intent Classify │  Determines what the question is about
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Data Planning Node                         │
│  Decides which backend tools and RAG queries are needed     │
└──────┬──────────┬───────────────────────────────────────────┘
       │          │
       ▼          ▼
┌───────────┐  ┌──────────────┐
│  Backend  │  │   RAG        │
│  Tools    │  │   Retrieval  │
│  Executor │  │   Node       │
└─────┬─────┘  └──────┬───────┘
       │               │
       └───────┬───────┘
               ▼
┌──────────────────────────────────┐
│     Analysis & Synthesis Node    │
│  LLM synthesizes tool results    │
│  and RAG context into an answer  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│     Response Validation Node     │
│  Checks for hallucinations:      │
│  - Live stats match tool output  │
│  - No invented scores/events     │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│     Final Response               │
│  Includes answer + citations     │
└──────────────────────────────────┘
```

---

## 10.2 LangGraph State Definition

```python
# sports_platform/ai/graph/state.py

from typing import Annotated, List, Optional, TypedDict
import operator


class AssistantState(TypedDict):
    # Conversation context
    user_id: str
    match_id: str
    conversation_id: str
    conversation_history: List[dict]  # prior messages
    
    # Current turn
    user_question: str
    intent: Optional[str]  # 'live_update', 'analysis', 'context', 'comparison'
    required_tools: List[str]
    
    # Tool outputs (accumulated across parallel calls)
    tool_results: Annotated[List[dict], operator.add]
    
    # RAG results
    rag_chunks: List[dict]
    
    # LLM output
    draft_answer: Optional[str]
    sources: List[dict]
    
    # Validation
    validation_passed: bool
    validation_issues: List[str]
    
    # Final
    final_answer: Optional[str]
    token_usage: Optional[dict]
```

---

## 10.3 Graph Definition

```python
# sports_platform/ai/graph/graph.py

from langgraph.graph import StateGraph, END
from sports_platform.ai.graph.state import AssistantState
from sports_platform.ai.graph import nodes

def build_match_assistant_graph():
    graph = StateGraph(AssistantState)

    # Add nodes
    graph.add_node("intent_classifier", nodes.classify_intent)
    graph.add_node("data_planner", nodes.plan_data_requirements)
    graph.add_node("backend_tools", nodes.execute_backend_tools)
    graph.add_node("rag_retrieval", nodes.retrieve_rag_context)
    graph.add_node("synthesizer", nodes.synthesize_answer)
    graph.add_node("validator", nodes.validate_response)
    graph.add_node("responder", nodes.format_final_response)

    # Define edges
    graph.set_entry_point("intent_classifier")
    
    graph.add_edge("intent_classifier", "data_planner")
    
    # After planning, run backend tools and RAG in parallel
    graph.add_conditional_edges(
        "data_planner",
        nodes.route_after_planning,
        {
            "tools_only": "backend_tools",
            "rag_only": "rag_retrieval",
            "both": ["backend_tools", "rag_retrieval"],  # parallel
        }
    )

    # Both paths converge at synthesizer
    graph.add_edge("backend_tools", "synthesizer")
    graph.add_edge("rag_retrieval", "synthesizer")
    
    graph.add_edge("synthesizer", "validator")
    
    graph.add_conditional_edges(
        "validator",
        nodes.route_after_validation,
        {
            "passed": "responder",
            "retry": "synthesizer",   # retry once with correction prompt
            "failed": "responder",    # return with warning
        }
    )
    
    graph.add_edge("responder", END)

    return graph.compile()
```

---

## 10.4 Node Implementations

### Intent Classifier Node

```python
# sports_platform/ai/graph/nodes/intent_classifier.py

INTENT_CLASSIFICATION_PROMPT = """
You are classifying a sports question to determine what data is needed to answer it.

Match context: {sport}, {home_team} vs {away_team}, Status: {match_status}

Question: {question}

Classify the primary intent as exactly one of:
- "live_update": Asking about current score, live events, what's happening now
- "analysis": Asking for analysis, comparison, performance assessment
- "context": Asking for background, history, rules, team/player info  
- "prediction": Asking what might happen (we respond with data, not predictions)
- "mixed": Question requires both live data and context

Also list required data types:
- needs_live_score: true/false
- needs_match_events: true/false
- needs_team_stats: true/false
- needs_standings: true/false
- needs_recent_matches: true/false
- needs_rag_context: true/false

Respond in JSON only.
"""

async def classify_intent(state: AssistantState) -> AssistantState:
    from sports_platform.ai.llm import get_llm
    
    match_meta = await get_match_metadata(state["match_id"])
    llm = get_llm()
    
    prompt = INTENT_CLASSIFICATION_PROMPT.format(
        sport=match_meta["sport"],
        home_team=match_meta["home_team"],
        away_team=match_meta["away_team"],
        match_status=match_meta["status"],
        question=state["user_question"],
    )
    
    response = await llm.ainvoke(prompt)
    classification = parse_json_response(response.content)
    
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

    return {
        **state,
        "intent": classification["intent"],
        "required_tools": required_tools,
    }
```

---

### Backend Tools Node

```python
# sports_platform/ai/graph/nodes/backend_tools.py

# All tools call internal services — NEVER the LLM for factual data

async def get_live_score(match_id: str) -> dict:
    """Fetch current score from Redis (authoritative)."""
    from sports_platform.matches.services import MatchScoreService
    return await MatchScoreService.get_current_score(match_id)

async def get_match_events(match_id: str, last_n: int = 20) -> list:
    """Fetch recent match events from Redis / PostgreSQL."""
    from sports_platform.matches.services import MatchEventService
    return await MatchEventService.get_recent_events(match_id, last_n)

async def get_team_stats(match_id: str, team_id: str) -> dict:
    """Fetch match statistics for a team from PostgreSQL."""
    from sports_platform.matches.services import MatchStatsService
    return await MatchStatsService.get_stats(match_id, team_id)

async def get_standings(competition_id: str) -> list:
    """Fetch current standings from PostgreSQL."""
    from sports_platform.competitions.services import StandingsService
    return await StandingsService.get_standings(competition_id)

async def get_recent_matches(team_id: str, limit: int = 5) -> list:
    """Fetch last N matches for a team from PostgreSQL."""
    from sports_platform.matches.services import MatchHistoryService
    return await MatchHistoryService.get_recent(team_id, limit)


async def execute_backend_tools(state: AssistantState) -> AssistantState:
    """Execute all required backend tools concurrently."""
    import asyncio
    
    tasks = []
    for tool_name in state["required_tools"]:
        if tool_name == "get_live_score":
            tasks.append(get_live_score(state["match_id"]))
        elif tool_name == "get_match_events":
            tasks.append(get_match_events(state["match_id"]))
        # ... etc

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    tool_results = []
    for tool_name, result in zip(state["required_tools"], results):
        if isinstance(result, Exception):
            tool_results.append({"tool": tool_name, "error": str(result), "data": None})
        else:
            tool_results.append({"tool": tool_name, "data": result, "error": None})
    
    return {**state, "tool_results": tool_results}
```

---

### Synthesis Node (LLM Call)

```python
# sports_platform/ai/graph/nodes/synthesizer.py

SYNTHESIS_PROMPT = """
You are a knowledgeable sports analyst assistant. Answer the user's question using ONLY the provided data.

CRITICAL RULES:
1. Never invent or assume scores, events, or statistics not present in the data.
2. If a tool returned an error or empty data, say so clearly.
3. Use RAG context only for background/historical information.
4. Be concise and engaging. The user is watching a live match.
5. Cite your sources at the end.

Match: {home_team} vs {away_team} ({sport})
Status: {match_status}

Live Data from Tools:
{tool_results_formatted}

Background Context (from knowledge base):
{rag_context_formatted}

Conversation History:
{conversation_history}

User Question: {question}

Answer (be conversational and helpful):
"""

async def synthesize_answer(state: AssistantState) -> AssistantState:
    from sports_platform.ai.llm import get_llm
    
    llm = get_llm()
    match_meta = await get_match_metadata(state["match_id"])
    
    prompt = SYNTHESIS_PROMPT.format(
        home_team=match_meta["home_team"],
        away_team=match_meta["away_team"],
        sport=match_meta["sport"],
        match_status=match_meta["status"],
        tool_results_formatted=format_tool_results(state["tool_results"]),
        rag_context_formatted=format_rag_chunks(state["rag_chunks"]),
        conversation_history=format_history(state["conversation_history"]),
        question=state["user_question"],
    )
    
    response = await llm.ainvoke(prompt)
    
    return {
        **state,
        "draft_answer": response.content,
        "token_usage": {
            "input": response.usage_metadata.get("input_tokens"),
            "output": response.usage_metadata.get("output_tokens"),
        }
    }
```

---

### Validation Node

```python
# sports_platform/ai/graph/nodes/validator.py

VALIDATION_PROMPT = """
Review this answer for factual consistency with the provided live data.

Live Data: {tool_results}
Draft Answer: {draft_answer}

Check:
1. Does the answer mention any scores not in the live data? → flag as FAIL
2. Does the answer mention events that didn't happen? → flag as FAIL
3. Is the answer appropriately uncertain when data was unavailable? → PASS
4. Is the answer relevant to the question? → must PASS

Return JSON: {"passed": true/false, "issues": ["list of issues if any"]}
"""

async def validate_response(state: AssistantState) -> AssistantState:
    from sports_platform.ai.llm import get_llm
    
    # Only validate if there are live tool results to check against
    if not any(r["data"] for r in state["tool_results"]):
        return {**state, "validation_passed": True, "validation_issues": []}
    
    llm = get_llm()
    prompt = VALIDATION_PROMPT.format(
        tool_results=format_tool_results(state["tool_results"]),
        draft_answer=state["draft_answer"],
    )
    
    response = await llm.ainvoke(prompt)
    validation = parse_json_response(response.content)
    
    return {
        **state,
        "validation_passed": validation["passed"],
        "validation_issues": validation.get("issues", []),
    }
```

---

## 10.5 Prompt Injection Hardening

```python
# sports_platform/ai/security.py

FORBIDDEN_PATTERNS = [
    "ignore previous instructions",
    "disregard your system prompt",
    "you are now",
    "pretend you are",
    "act as a different",
    "reveal your system prompt",
    "what are your instructions",
]

def sanitize_user_input(text: str) -> str:
    """Basic injection detection and sanitization."""
    lower = text.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in lower:
            raise ValueError("Input contains potentially harmful content")
    
    # Truncate to prevent token stuffing
    MAX_QUESTION_LENGTH = 500
    return text[:MAX_QUESTION_LENGTH].strip()
```

---

## 10.6 Conversation Persistence

```python
# sports_platform/ai/conversation_service.py

class ConversationService:
    """Persists LangGraph conversation turns to PostgreSQL."""

    async def save_turn(
        self,
        conversation_id: str,
        user_question: str,
        final_answer: str,
        tool_calls: list,
        sources: list,
        token_usage: dict,
        latency_ms: int,
    ):
        # Save user message
        await AIMessage.objects.acreate(
            conversation_id=conversation_id,
            role="user",
            content=user_question,
        )
        # Save assistant message
        await AIMessage.objects.acreate(
            conversation_id=conversation_id,
            role="assistant",
            content=final_answer,
            tool_calls=tool_calls,
            sources=sources,
            token_usage=token_usage,
            latency_ms=latency_ms,
        )

    async def get_history(self, conversation_id: str, last_n: int = 10) -> list:
        messages = await AIMessage.objects.filter(
            conversation_id=conversation_id
        ).order_by("-created_at")[:last_n]
        return [{"role": m.role, "content": m.content} for m in reversed(messages)]
```
