"""
Matches serializers.
"""
from rest_framework import serializers

from sports_platform.matches.models import (
    Match,
    MatchEvent,
    MatchOddsCurrent,
    MatchOddsHistory,
    MatchScore,
)
from sports_platform.sports.serializers import TeamListSerializer, CompetitionListSerializer, SportSerializer


class MatchListSerializer(serializers.ModelSerializer):
    home_team = TeamListSerializer(read_only=True)
    away_team = TeamListSerializer(read_only=True)
    sport_slug = serializers.CharField(source="sport.slug", read_only=True)
    competition_name = serializers.CharField(source="competition.name", read_only=True)

    class Meta:
        model = Match
        fields = [
            "id", "sport_slug", "competition_name",
            "home_team", "away_team",
            "scheduled_at", "started_at", "status",
            "venue", "round", "provider_match_id",
        ]


class MatchDetailSerializer(serializers.ModelSerializer):
    home_team = TeamListSerializer(read_only=True)
    away_team = TeamListSerializer(read_only=True)
    sport = SportSerializer(read_only=True)
    competition = CompetitionListSerializer(read_only=True)

    class Meta:
        model = Match
        fields = [
            "id", "sport", "competition",
            "home_team", "away_team",
            "scheduled_at", "started_at", "completed_at",
            "status", "venue", "round", "metadata",
            "source_provider", "provider_match_id",
            "created_at", "updated_at",
        ]


class MatchEventSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source="player.name", default=None, read_only=True)
    secondary_player_name = serializers.CharField(
        source="secondary_player.name", default=None, read_only=True
    )
    team_name = serializers.CharField(source="team.name", default=None, read_only=True)

    class Meta:
        model = MatchEvent
        fields = [
            "id", "event_type", "event_sequence", "occurred_at",
            "minute", "over_ball",
            "player_name", "secondary_player_name", "team_name",
            "description", "event_data",
        ]


class MatchScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchScore
        fields = ["score_data", "sequence_number", "updated_at"]


class MatchOddsCurrentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchOddsCurrent
        fields = [
            "id",
            "provider_name",
            "market_type",
            "bookmaker",
            "odds_data",
            "is_open",
            "updated_at",
        ]


class MatchOddsHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchOddsHistory
        fields = [
            "id",
            "provider_name",
            "market_type",
            "bookmaker",
            "odds_data",
            "recorded_at",
        ]
