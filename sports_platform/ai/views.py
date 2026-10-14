"""
AI Views — Milestone 10.

Endpoints:
- POST /api/v1/ai/matches/{id}/ask
- GET  /api/v1/ai/matches/{id}/conversations
- GET  /api/v1/ai/conversations/{id}/messages/
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
import uuid

from sports_platform.ai.models import AIConversation, AIMessage
from sports_platform.ai.serializers import (
    AIAskRequestSerializer,
    AIAskResponseSerializer,
    AIConversationSerializer,
    AIMessageSerializer,
)
from sports_platform.ai.security import sanitize_user_input, PromptInjectionError
from sports_platform.ai.rate_limit import AIRateLimiter, AIRateLimitExceeded
from sports_platform.ai.graph.graph import execute_match_assistant
from sports_platform.matches.models import Match


class MatchAIAssistantAskView(APIView):
    """
    POST /api/v1/ai/matches/{id}/ask
    Sends a natural language question about the match to the LangGraph AI Assistant.
    Enforces prompt injection detection, token validation, and 20 req/hour rate limiting.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, match_id, *args, **kwargs):
        # 1. Validate match exists
        try:
            match_uuid = uuid.UUID(str(match_id))
            if not Match.objects.filter(id=match_uuid).exists():
                return Response(
                    {"error": f"Match with ID '{match_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid match ID format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Rate limit check (20 requests / hour / user)
        rate_limiter = AIRateLimiter()
        try:
            rate_limiter.check_and_increment(str(request.user.id))
        except AIRateLimitExceeded as e:
            return Response(
                {"error": str(e), "code": "rate_limit_exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # 3. Validate request payload
        serializer = AIAskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_question = serializer.validated_data["question"]
        conversation_id = serializer.validated_data.get("conversation_id")

        # 4. Prompt injection sanitization
        try:
            sanitized_question = sanitize_user_input(raw_question)
        except PromptInjectionError as e:
            return Response(
                {"error": str(e), "code": "prompt_injection_detected"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5. Execute LangGraph Assistant
        result = execute_match_assistant(
            user_id=str(request.user.id),
            match_id=str(match_uuid),
            question=sanitized_question,
            conversation_id=str(conversation_id) if conversation_id else None,
        )

        response_serializer = AIAskResponseSerializer(result)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class MatchAIConversationsView(ListAPIView):
    """
    GET /api/v1/ai/matches/{id}/conversations
    Lists past conversation sessions for the authenticated user on this match.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AIConversationSerializer

    def get_queryset(self):
        match_id = self.kwargs.get("match_id")
        return (
            AIConversation.objects.filter(
                user=self.request.user,
                match_id=match_id,
            )
            .prefetch_related("messages")
            .order_by("-updated_at")
        )


class AIConversationMessagesView(ListAPIView):
    """
    GET /api/v1/ai/conversations/{id}/messages/
    Retrieves full message turn history for a conversation session.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AIMessageSerializer

    def get_queryset(self):
        conv_id = self.kwargs.get("id")
        return AIMessage.objects.filter(
            conversation__id=conv_id,
            conversation__user=self.request.user,
        ).order_by("created_at")
