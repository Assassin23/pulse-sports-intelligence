"""
Preferences admin configuration.
"""
from django.contrib import admin

from sports_platform.preferences.models import (
    UserFollowedEntity,
    UserNotificationPreference,
    UserSportPreference,
)


@admin.register(UserSportPreference)
class UserSportPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "sport", "created_at"]
    list_filter = ["sport"]
    search_fields = ["user__email", "user__username"]


@admin.register(UserFollowedEntity)
class UserFollowedEntityAdmin(admin.ModelAdmin):
    list_display = ["user", "sport", "entity_type", "entity_id", "created_at"]
    list_filter = ["sport", "entity_type"]
    search_fields = ["user__email", "user__username", "entity_id"]


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "sport", "notification_type", "is_enabled", "channel_websocket", "channel_push"]
    list_filter = ["sport", "notification_type", "is_enabled"]
    search_fields = ["user__email", "user__username"]
