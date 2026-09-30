"""
Sports serializers for reference data endpoints.
"""
from rest_framework import serializers

from sports_platform.sports.models import Competition, Country, Player, Sport, Team


class SportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sport
        fields = ["id", "slug", "name", "icon_url"]


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "iso_code", "name"]


class TeamSerializer(serializers.ModelSerializer):
    sport = SportSerializer(read_only=True)
    country = CountrySerializer(read_only=True)

    class Meta:
        model = Team
        fields = ["id", "name", "short_name", "logo_url", "team_type", "sport", "country"]


class TeamListSerializer(serializers.ModelSerializer):
    """Lighter serializer for lists — excludes nested objects."""

    country_name = serializers.CharField(source="country.name", read_only=True, default=None)

    class Meta:
        model = Team
        fields = ["id", "name", "short_name", "logo_url", "team_type", "country_name"]


class CompetitionSerializer(serializers.ModelSerializer):
    sport = SportSerializer(read_only=True)
    country = CountrySerializer(read_only=True)

    class Meta:
        model = Competition
        fields = [
            "id", "name", "short_name", "season", "competition_type",
            "logo_url", "sport", "country",
        ]


class CompetitionListSerializer(serializers.ModelSerializer):
    """Lighter serializer for lists."""

    country_name = serializers.CharField(source="country.name", read_only=True, default=None)

    class Meta:
        model = Competition
        fields = ["id", "name", "short_name", "season", "competition_type", "logo_url", "country_name"]


class PlayerSerializer(serializers.ModelSerializer):
    nationality = CountrySerializer(read_only=True)

    class Meta:
        model = Player
        fields = ["id", "name", "position", "photo_url", "date_of_birth", "nationality"]


class PlayerListSerializer(serializers.ModelSerializer):
    """Lighter serializer for lists."""

    nationality_name = serializers.CharField(source="nationality.name", read_only=True, default=None)

    class Meta:
        model = Player
        fields = ["id", "name", "position", "photo_url", "nationality_name"]
