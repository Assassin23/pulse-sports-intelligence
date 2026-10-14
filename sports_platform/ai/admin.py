from django.contrib import admin
from sports_platform.ai.models import AIConversation, AIMessage


class AIMessageInline(admin.TabularInline):
    model = AIMessage
    extra = 0
    fields = ["role", "content", "latency_ms", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "match", "title", "updated_at", "created_at"]
    search_fields = ["user__email", "match__id", "title"]
    inlines = [AIMessageInline]


@admin.register(AIMessage)
class AIMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "role", "latency_ms", "created_at"]
    list_filter = ["role", "created_at"]
    search_fields = ["content", "conversation__id"]
