"""
Matches Django app models.

Stores discovered match data processed from Kafka match.discovered events.
Redis is authoritative for live state; PostgreSQL is the durable record.
"""
import uuid

from django.db import models


class MatchStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    LIVE = "live", "Live"
    HALF_TIME = "half_time", "Half Time"
    PAUSED = "paused", "Paused"
    COMPLETED = "completed", "Completed"
    POSTPONED = "postponed", "Postponed"
    CANCELLED = "cancelled", "Cancelled"
    SUSPENDED = "suspended", "Suspended"
    INTERRUPTED = "interrupted", "Interrupted"
    ABANDONED = "abandoned", "Abandoned"


class Match(models.Model):
    """
    A sports match / fixture.

    Discovered via Kafka match.discovered events from the ingestion pipeline.
    Status transitions: scheduled → live → completed (or postponed/cancelled).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sport = models.ForeignKey(
        "sports.Sport", on_delete=models.PROTECT, related_name="matches"
    )
    competition = models.ForeignKey(
        "sports.Competition", on_delete=models.PROTECT, related_name="matches"
    )
    home_team = models.ForeignKey(
        "sports.Team", on_delete=models.PROTECT, related_name="home_matches"
    )
    away_team = models.ForeignKey(
        "sports.Team", on_delete=models.PROTECT, related_name="away_matches"
    )
    scheduled_at = models.DateTimeField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=MatchStatus.choices,
        default=MatchStatus.SCHEDULED,
        db_index=True,
    )
    venue = models.CharField(max_length=300, blank=True)
    round = models.CharField(max_length=50, blank=True)
    # Provider that first discovered this match
    source_provider = models.CharField(max_length=100)
    # Provider's external match ID (for polling)
    provider_match_id = models.CharField(max_length=100, db_index=True)
    # Sport-specific extra metadata (e.g., innings info, format)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "matches"
        indexes = [
            models.Index(
                fields=["status"],
                condition=models.Q(status="live"),
                name="idx_matches_live",
            ),
            models.Index(
                fields=["scheduled_at"],
                condition=models.Q(status="scheduled"),
                name="idx_matches_scheduled",
            ),
            models.Index(fields=["competition", "scheduled_at"], name="idx_matches_competition"),
            models.Index(fields=["home_team", "scheduled_at"], name="idx_matches_home_team"),
            models.Index(fields=["away_team", "scheduled_at"], name="idx_matches_away_team"),
            models.Index(fields=["updated_at"], name="idx_matches_updated"),
        ]
        unique_together = [("source_provider", "provider_match_id")]

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} ({self.scheduled_at.date()})"


class MatchScore(models.Model):
    """
    Current match score snapshot.

    Redis is the live authoritative source.
    This table is updated by ScoreProcessorConsumer for durability
    and rebuilt-from queries if Redis is unavailable.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name="score"
    )
    # Sport-specific score data (flexible JSONB)
    score_data = models.JSONField(default=dict)
    sequence_number = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "match_scores"

    def __str__(self):
        return f"Score for {self.match} — seq {self.sequence_number}"


class MatchEvent(models.Model):
    """
    An in-match event: goal, wicket, card, substitution, etc.

    Written by EventProcessorConsumer. Deduplication via
    (match, source_provider, event_sequence) unique constraint.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="events"
    )
    sport = models.ForeignKey("sports.Sport", on_delete=models.PROTECT)
    event_type = models.CharField(max_length=50, db_index=True)
    event_sequence = models.IntegerField()
    occurred_at = models.DateTimeField(null=True, blank=True)
    minute = models.IntegerField(null=True, blank=True)
    over_ball = models.CharField(max_length=10, blank=True)  # Cricket: "14.3"
    player = models.ForeignKey(
        "sports.Player",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="match_events",
    )
    secondary_player = models.ForeignKey(
        "sports.Player",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="secondary_match_events",
    )
    team = models.ForeignKey(
        "sports.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="match_events",
    )
    description = models.TextField(blank=True)
    event_data = models.JSONField(default=dict)  # Sport-specific extras
    source_provider = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "match_events"
        unique_together = [("match", "source_provider", "event_sequence")]
        indexes = [
            models.Index(fields=["match", "event_sequence"], name="idx_match_events_match"),
            models.Index(fields=["match", "event_type"], name="idx_match_events_type"),
        ]
        ordering = ["event_sequence"]

    def __str__(self):
        return f"{self.event_type} (seq {self.event_sequence}) in {self.match}"


class MatchOddsCurrent(models.Model):
    """
    Current odds snapshot per match, provider, market, and bookmaker.
    Fast durable record upserted by OddsProcessorConsumer.
    Odds are strictly for informational analysis (no wagering/betting).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="odds_current"
    )
    provider_name = models.CharField(max_length=100, db_index=True)
    market_type = models.CharField(max_length=50, db_index=True)
    bookmaker = models.CharField(max_length=100)
    odds_data = models.JSONField(default=dict)
    is_open = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "match_odds_current"
        unique_together = [("match", "provider_name", "market_type", "bookmaker")]
        indexes = [
            models.Index(fields=["match", "market_type"], name="idx_odds_curr_match_mkt"),
        ]

    def __str__(self):
        return f"Current odds {self.market_type} ({self.bookmaker}) for {self.match_id}"


class MatchOddsHistory(models.Model):
    """
    Append-only historical odds movements for time-series charts and line movement analysis.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="odds_history"
    )
    provider_name = models.CharField(max_length=100, db_index=True)
    market_type = models.CharField(max_length=50, db_index=True)
    bookmaker = models.CharField(max_length=100)
    odds_data = models.JSONField(default=dict)
    recorded_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "match_odds_history"
        unique_together = [("match", "provider_name", "market_type", "recorded_at")]
        indexes = [
            models.Index(
                fields=["match", "market_type", "recorded_at"],
                name="idx_odds_hist_match_mkt_time",
            ),
        ]
        ordering = ["recorded_at"]

    def __str__(self):
        return f"Historical odds {self.market_type} at {self.recorded_at} for {self.match_id}"
