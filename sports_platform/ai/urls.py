"""
AI URLs — Milestone 10.
Routes under /api/v1/ai/
"""
from django.urls import path
from sports_platform.ai.views import (
    MatchAIAssistantAskView,
    MatchAIConversationsView,
    AIConversationMessagesView,
)

app_name = "ai"

urlpatterns = [
    path("matches/<uuid:match_id>/ask", MatchAIAssistantAskView.as_view(), name="match-ask-no-slash"),
    path("matches/<uuid:match_id>/ask/", MatchAIAssistantAskView.as_view(), name="match-ask"),
    path("matches/<uuid:match_id>/conversations", MatchAIConversationsView.as_view(), name="match-conversations-no-slash"),
    path("matches/<uuid:match_id>/conversations/", MatchAIConversationsView.as_view(), name="match-conversations"),
    path("conversations/<uuid:id>/messages/", AIConversationMessagesView.as_view(), name="conversation-messages"),
]
