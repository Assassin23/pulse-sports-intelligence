"""
User preferences and notification settings models.
"""
import uuid

from django.conf import settings
from django.db import models

from sports_platform.sports.models import Sport


class UserSportPreference(models.Model):
    """
    Which sports a user follows (up to a max of 3).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sport_preferences",
    )
    sport = models.ForeignKey(
        Sport,
        on_delete=models.CASCADE,
        related_name="user_preferences",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_sport_preferences"
        unique_together = [("user", "sport")]
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.sport.slug}"


class UserFollowedEntity(models.Model):
    """
    Specific entities (team, competition, country, player) a user follows.
    """

    ENTITY_TYPES = [
        ("team", "Team"),
        ("competition", "Competition"),
        ("country", "Country"),
        ("player", "Player"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followed_entities",
    )
    sport = models.ForeignKey(
        Sport,
        on_delete=models.CASCADE,
        related_name="user_follows",
    )
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPES)
    entity_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_followed_entities"
        unique_together = [("user", "entity_type", "entity_id")]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["user", "sport"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} follows {self.entity_type}:{self.entity_id} ({self.sport.slug})"


class UserNotificationPreference(models.Model):
    """
    Granular notification preferences per sport and event type.
    """

    NOTIFICATION_TYPES = [
        ("match_start", "Match Start"),
        ("goal", "Goal"),
        ("wicket", "Wicket"),
        ("red_card", "Red Card"),
        ("match_end", "Match End"),
        ("breaking_news", "Breaking News"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    sport = models.ForeignKey(
        Sport,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    is_enabled = models.BooleanField(default=True)
    channel_websocket = models.BooleanField(default=True)
    channel_push = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_notification_preferences"
        unique_together = [("user", "sport", "notification_type")]
        indexes = [
            models.Index(fields=["user", "sport"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.sport.slug} - {self.notification_type}: {self.is_enabled}"
