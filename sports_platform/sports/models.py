"""
Sports reference data models.
Includes Sport, Country, Team, Competition, Player, and ProviderEntityMapping.
These are the core domain entities that preferences and matches reference.
"""
import uuid

from django.db import models


class Sport(models.Model):
    """Top-level sport category (cricket, football, tennis, etc.)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    icon_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sports"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Country(models.Model):
    """ISO country for team nationality and competition geography."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    iso_code = models.CharField(max_length=3, unique=True, db_index=True)
    name = models.CharField(max_length=100, db_index=True)

    class Meta:
        db_table = "countries"
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self) -> str:
        return f"{self.name} ({self.iso_code})"


class Competition(models.Model):
    """League, cup, or tournament (e.g., IPL, Premier League)."""

    COMPETITION_TYPES = [
        ("league", "League"),
        ("cup", "Cup"),
        ("international", "International"),
        ("friendly", "Friendly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="competitions")
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="competitions"
    )
    name = models.CharField(max_length=200, db_index=True)
    short_name = models.CharField(max_length=50, blank=True)
    season = models.CharField(max_length=20, blank=True)
    competition_type = models.CharField(
        max_length=20, choices=COMPETITION_TYPES, default="league"
    )
    logo_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "competitions"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["sport", "is_active"]),
            models.Index(fields=["country", "sport"]),
        ]

    def __str__(self) -> str:
        season_str = f" {self.season}" if self.season else ""
        return f"{self.name}{season_str}"


class Team(models.Model):
    """Club or national team."""

    TEAM_TYPES = [
        ("club", "Club"),
        ("national", "National"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="teams")
    country = models.ForeignKey(
        Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="teams"
    )
    name = models.CharField(max_length=200, db_index=True)
    short_name = models.CharField(max_length=50, blank=True)
    logo_url = models.URLField(max_length=500, blank=True)
    team_type = models.CharField(max_length=10, choices=TEAM_TYPES, default="club")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "teams"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["sport", "is_active"]),
            models.Index(fields=["sport", "team_type"]),
        ]

    def __str__(self) -> str:
        return self.name


class Player(models.Model):
    """Individual player profile."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="players")
    nationality = models.ForeignKey(
        Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="players"
    )
    name = models.CharField(max_length=200, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    position = models.CharField(max_length=50, blank=True)
    photo_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "players"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["sport", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name


class ProviderEntityMapping(models.Model):
    """
    Maps external provider IDs to internal UUIDs.
    Decouples internal entity IDs from provider-specific IDs.
    Ensures a provider change does not require changing any internal references.
    """

    ENTITY_TYPES = [
        ("match", "Match"),
        ("team", "Team"),
        ("player", "Player"),
        ("competition", "Competition"),
        ("country", "Country"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_name = models.CharField(max_length=50, db_index=True)
    provider_entity_id = models.CharField(max_length=200)
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPES)
    internal_entity_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "provider_entity_mappings"
        unique_together = [("provider_name", "provider_entity_id", "entity_type")]
        indexes = [
            models.Index(
                fields=["provider_name", "entity_type", "provider_entity_id"],
                name="idx_provider_mapping_lookup",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}:{self.entity_type}:{self.provider_entity_id}"
