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
