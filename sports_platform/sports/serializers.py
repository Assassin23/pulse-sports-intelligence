"""
Sports reference data serializers.
"""
from rest_framework import serializers

from sports_platform.sports.models import Competition, Country, Player, Sport, Team


class SportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sport
        fields = ["id", "slug", "name", "icon_url", "is_active"]


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "iso_code", "name"]


# ── Team Serializers ──────────────────────────────────────────────────────────

class TeamListSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    sport_slug = serializers.CharField(source="sport.slug", read_only=True)

    class Meta:
        model = Team
        fields = ["id", "name", "short_name", "logo_url", "team_type", "country", "sport_slug"]


class TeamDetailSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    sport = SportSerializer(read_only=True)

    class Meta:
        model = Team
        fields = ["id", "name", "short_name", "logo_url", "team_type", "country", "sport", "created_at"]


# ── Competition Serializers ───────────────────────────────────────────────────

class CompetitionListSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    sport_slug = serializers.CharField(source="sport.slug", read_only=True)

    class Meta:
        model = Competition
        fields = [
            "id", "name", "short_name", "logo_url",
            "competition_type", "season", "country", "sport_slug",
        ]


class CompetitionDetailSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    sport = SportSerializer(read_only=True)

    class Meta:
        model = Competition
        fields = [
            "id", "name", "short_name", "logo_url",
            "competition_type", "season", "country", "sport", "created_at",
        ]


# ── Player Serializers ────────────────────────────────────────────────────────

class PlayerListSerializer(serializers.ModelSerializer):
    nationality = CountrySerializer(read_only=True)
    sport_slug = serializers.CharField(source="sport.slug", read_only=True)

    class Meta:
        model = Player
        fields = [
            "id", "name", "position", "photo_url", "nationality", "sport_slug",
        ]


class PlayerDetailSerializer(serializers.ModelSerializer):
    nationality = CountrySerializer(read_only=True)
    sport = SportSerializer(read_only=True)

    class Meta:
        model = Player
        fields = [
            "id", "name", "position", "date_of_birth", "photo_url",
            "nationality", "sport", "created_at",
        ]
