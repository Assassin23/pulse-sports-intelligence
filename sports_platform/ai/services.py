"""
AI Conversation Service — Milestone 10.

Manages conversation persistence, message histories, citations, and token logs.
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from django.db import transaction

from sports_platform.ai.models import AIConversation, AIMessage
from sports_platform.matches.models import Match
from sports_platform.users.models import User

logger = logging.getLogger(__name__)


class ConversationService:
    """Handles persistence of AI Assistant conversations and messages."""

    @staticmethod
    def get_or_create_conversation(
        user_id: str,
        match_id: str,
        conversation_id: Optional[str] = None,
    ) -> AIConversation:
        """
        Retrieves existing conversation or creates a new one for user and match.
        """
        if conversation_id:
            try:
                conv_uuid = uuid.UUID(str(conversation_id))
                conv = AIConversation.objects.filter(id=conv_uuid, user_id=user_id, match_id=match_id).first()
                if conv:
                    return conv
            except (ValueError, TypeError):
                pass

        user = User.objects.get(id=user_id)
        match = Match.objects.get(id=match_id)
        return AIConversation.objects.create(
            user=user,
            match=match,
            title="",
        )

    @staticmethod
    def get_history(conversation_id: str, last_n: int = 10) -> List[Dict[str, str]]:
        """
        Fetch the most recent turns in chronological order for conversation context.
        """
        messages = (
            AIMessage.objects.filter(conversation_id=conversation_id)
            .order_by("-created_at")[:last_n]
        )
        return [{"role": m.role, "content": m.content} for m in reversed(messages)]

    @staticmethod
    def save_turn(
        conversation_id: str,
        user_question: str,
        final_answer: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        token_usage: Optional[Dict[str, int]] = None,
        latency_ms: Optional[int] = None,
    ) -> AIMessage:
        """
        Persists a full conversational turn (user query + assistant response).
        """
        with transaction.atomic():
            conv = AIConversation.objects.select_for_update().get(id=conversation_id)
            if not conv.title:
                conv.title = user_question[:80].strip()
                conv.save(update_fields=["title", "updated_at"])
            else:
                conv.save(update_fields=["updated_at"])

            # 1. User message
            AIMessage.objects.create(
                conversation=conv,
                role="user",
                content=user_question,
            )

            # 2. Assistant message
            assistant_msg = AIMessage.objects.create(
                conversation=conv,
                role="assistant",
                content=final_answer,
                tool_calls=tool_calls or [],
                sources=sources or [],
                token_usage=token_usage or {},
                latency_ms=latency_ms,
            )

        return assistant_msg
