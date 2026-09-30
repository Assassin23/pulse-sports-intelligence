"""
Sports reference data views.
Search endpoints for teams, competitions, players, and sports.
"""
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sports_platform.sports.models import Competition, Country, Player, Sport, Team
from sports_platform.sports.serializers import (
    CompetitionListSerializer,
    CountrySerializer,
    PlayerListSerializer,
    SportSerializer,
    TeamListSerializer,
)


class SportListView(APIView):
    """GET /api/v1/sports/ — list all active sports."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        sports = Sport.objects.filter(is_active=True)
        return Response({"sports": SportSerializer(sports, many=True).data})


class SportTeamsView(APIView):
    """
    GET /api/v1/sports/{slug}/teams/
    Search teams within a sport.
    Query params: q (name search), country (country iso_code), type (club/national)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, slug: str) -> Response:
        sport = get_object_or_404(Sport, slug=slug, is_active=True)

        qs = Team.objects.filter(sport=sport, is_active=True).select_related("country")

        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)

        country_code = request.query_params.get("country", "").strip().upper()
        if country_code:
            qs = qs.filter(country__iso_code=country_code)

        team_type = request.query_params.get("type", "").strip()
        if team_type in ["club", "national"]:
            qs = qs.filter(team_type=team_type)

        qs = qs[:50]  # Cap at 50 results
        return Response({"sport": slug, "teams": TeamListSerializer(qs, many=True).data})


class SportCompetitionsView(APIView):
    """
    GET /api/v1/sports/{slug}/competitions/
    Search competitions within a sport.
    Query params: q, country (iso_code)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, slug: str) -> Response:
        sport = get_object_or_404(Sport, slug=slug, is_active=True)

        qs = Competition.objects.filter(sport=sport, is_active=True).select_related("country")

        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)

        country_code = request.query_params.get("country", "").strip().upper()
        if country_code:
            qs = qs.filter(country__iso_code=country_code)

        qs = qs[:50]
        return Response(
            {"sport": slug, "competitions": CompetitionListSerializer(qs, many=True).data}
        )


class SportPlayersView(APIView):
    """
    GET /api/v1/sports/{slug}/players/
    Search players within a sport.
    Query params: q (name search), nationality (iso_code)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, slug: str) -> Response:
        sport = get_object_or_404(Sport, slug=slug, is_active=True)

        qs = Player.objects.filter(sport=sport, is_active=True).select_related("nationality")

        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)

        nationality = request.query_params.get("nationality", "").strip().upper()
        if nationality:
            qs = qs.filter(nationality__iso_code=nationality)

        qs = qs[:50]
        return Response(
            {"sport": slug, "players": PlayerListSerializer(qs, many=True).data}
        )


class CountryListView(APIView):
    """GET /api/v1/sports/countries/ — list all countries."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        countries = Country.objects.all().order_by("name")
        q = request.query_params.get("q", "").strip()
        if q:
            countries = countries.filter(name__icontains=q)
        countries = countries[:100]
        return Response({"countries": CountrySerializer(countries, many=True).data})
