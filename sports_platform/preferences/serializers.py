"""
Preferences serializers.
"""
from typing import Any, Dict, List
from rest_framework import serializers

from sports_platform.preferences.models import (
    UserFollowedEntity,
    UserNotificationPreference,
    UserSportPreference,
)
from sports_platform.sports.models import Competition, Country, Player, Sport, Team


class FollowEntitySerializer(serializers.Serializer):
    """Payload for following a single entity."""

    sport = serializers.CharField(max_length=50, help_text="Sport slug, e.g., 'cricket'")
    entity_type = serializers.ChoiceField(
        choices=["team", "competition", "country", "player"]
    )
    entity_id = serializers.UUIDField()


class BulkUpdatePreferencesSerializer(serializers.Serializer):
    """Payload for full preferences PUT."""

    sports = serializers.ListField(
        child=serializers.CharField(max_length=50),
        max_length=3,
        allow_empty=True,
    )
    following = serializers.ListField(
        child=FollowEntitySerializer(),
        required=False,
        default=list,
    )


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    sport_slug = serializers.CharField(source="sport.slug", read_only=True)

    class Meta:
        model = UserNotificationPreference
        fields = [
            "id",
            "sport_slug",
            "notification_type",
            "is_enabled",
            "channel_websocket",
            "channel_push",
            "updated_at",
        ]


class UserConsoleSessionSerializer(serializers.ModelSerializer):
    class Meta:
        from sports_platform.preferences.models import UserConsoleSession
        model = UserConsoleSession
        fields = [
            "pinned_matches",
            "active_match_id",
            "console_mode",
            "rotation_angle",
            "updated_at",
        ]


class UpdateUserConsoleSessionSerializer(serializers.Serializer):
    pinned_matches = serializers.ListField(
        child=serializers.CharField(max_length=64),
        max_length=4,
        required=False,
    )
    active_match_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    console_mode = serializers.CharField(max_length=30, required=False)
    rotation_angle = serializers.IntegerField(required=False)

    def validate_pinned_matches(self, value):
        if len(value) > 4:
            raise serializers.ValidationError("At most 4 matches can be pinned to the console.")
        return value


class NotificationLogSerializer(serializers.ModelSerializer):
    match_id = serializers.CharField(source="match.id", read_only=True, default=None)

    class Meta:
        from sports_platform.preferences.models import NotificationLog
        model = NotificationLog
        fields = [
            "id",
            "match_id",
            "notification_type",
            "title",
            "message",
            "data",
            "channel",
            "is_read",
            "created_at",
        ]
