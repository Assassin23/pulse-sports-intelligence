"""
AI Serializers — Milestone 10.
"""
from rest_framework import serializers
from sports_platform.ai.models import AIConversation, AIMessage


class AIMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = [
            "id",
            "role",
            "content",
            "tool_calls",
            "sources",
            "token_usage",
            "latency_ms",
            "created_at",
        ]


class AIConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(source="messages.count", read_only=True)
    recent_messages = serializers.SerializerMethodField()

    class Meta:
        model = AIConversation
        fields = [
            "id",
            "match_id",
            "title",
            "message_count",
            "created_at",
            "updated_at",
            "recent_messages",
        ]

    def get_recent_messages(self, obj):
        messages = obj.messages.order_by("-created_at")[:5]
        return AIMessageSerializer(reversed(list(messages)), many=True).data


class AIAskRequestSerializer(serializers.Serializer):
    question = serializers.CharField(required=True, min_length=2, max_length=500)
    conversation_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class AIAskResponseSerializer(serializers.Serializer):
    conversation_id = serializers.CharField()
    match_id = serializers.CharField()
    question = serializers.CharField()
    answer = serializers.CharField()
    sources = serializers.ListField(child=serializers.DictField())
    tool_calls = serializers.ListField(child=serializers.DictField())
    token_usage = serializers.DictField()
    latency_ms = serializers.IntegerField()
