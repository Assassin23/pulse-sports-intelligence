"""
Sports reference data views.
Complete REST endpoints for sports, teams, competitions, players, and countries.

Endpoints:
  GET /api/v1/sports/                        — list active sports
  GET /api/v1/sports/{slug}/                 — sport detail
  GET /api/v1/sports/countries/              — all countries
  GET /api/v1/sports/{slug}/teams/           — search teams in sport
  GET /api/v1/sports/teams/{id}/             — team detail
  GET /api/v1/sports/{slug}/competitions/    — search competitions in sport
  GET /api/v1/sports/competitions/{id}/      — competition detail
  GET /api/v1/sports/{slug}/players/         — search players in sport
  GET /api/v1/sports/players/{id}/           — player detail
"""
import uuid

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sports_platform.sports.models import Competition, Country, Player, Sport, Team
from sports_platform.sports.serializers import (
    CompetitionDetailSerializer,
    CompetitionListSerializer,
    CountrySerializer,
    PlayerDetailSerializer,
    PlayerListSerializer,
    SportSerializer,
    TeamDetailSerializer,
    TeamListSerializer,
)


class SportListView(APIView):
    """GET /api/v1/sports/ — list all active sports."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        sports = Sport.objects.filter(is_active=True).order_by("name")
        return Response({"sports": SportSerializer(sports, many=True).data})


class SportDetailView(APIView):
    """GET /api/v1/sports/{slug}/ — single sport detail."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, slug: str) -> Response:
        sport = get_object_or_404(Sport, slug=slug, is_active=True)
        return Response(SportSerializer(sport).data)


class CountryListView(APIView):
    """GET /api/v1/sports/countries/ — list all countries."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        q = request.query_params.get("q", "").strip()
        qs = Country.objects.all().order_by("name")
        if q:
            qs = qs.filter(name__icontains=q)
        return Response({"countries": CountrySerializer(qs[:100], many=True).data})


class TeamListView(APIView):
    """
    GET /api/v1/sports/{slug}/teams/
    Query params: q (name), country (iso_code), type (club/national)
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
        if team_type in ("club", "national"):
            qs = qs.filter(team_type=team_type)

        qs = qs.order_by("name")[:50]
        return Response({
            "sport": slug,
            "teams": TeamListSerializer(qs, many=True).data,
            "count": qs.count(),
        })


class TeamDetailView(APIView):
    """GET /api/v1/sports/teams/{id}/ — single team."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, id: uuid.UUID) -> Response:
        team = get_object_or_404(Team, id=id, is_active=True)
        return Response(TeamDetailSerializer(team).data)


class CompetitionListView(APIView):
    """
    GET /api/v1/sports/{slug}/competitions/
    Query params: q (name), country (iso_code), season, type (league/cup/international)
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

        season = request.query_params.get("season", "").strip()
        if season:
            qs = qs.filter(season=season)

        comp_type = request.query_params.get("type", "").strip()
        if comp_type in ("league", "cup", "international", "friendly"):
            qs = qs.filter(competition_type=comp_type)

        qs = qs.order_by("name")[:50]
        return Response({
            "sport": slug,
            "competitions": CompetitionListSerializer(qs, many=True).data,
            "count": qs.count(),
        })


class CompetitionDetailView(APIView):
    """GET /api/v1/sports/competitions/{id}/ — single competition."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, id: uuid.UUID) -> Response:
        comp = get_object_or_404(Competition, id=id, is_active=True)
        return Response(CompetitionDetailSerializer(comp).data)


class PlayerListView(APIView):
    """
    GET /api/v1/sports/{slug}/players/
    Query params: q (name), nationality (iso_code), position
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, slug: str) -> Response:
        sport = get_object_or_404(Sport, slug=slug, is_active=True)
        qs = Player.objects.filter(sport=sport, is_active=True).select_related("nationality")

        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)

        nationality_code = request.query_params.get("nationality", "").strip().upper()
        if nationality_code:
            qs = qs.filter(nationality__iso_code=nationality_code)

        position = request.query_params.get("position", "").strip()
        if position:
            qs = qs.filter(position__icontains=position)

        qs = qs.order_by("name")[:50]
        return Response({
            "sport": slug,
            "players": PlayerListSerializer(qs, many=True).data,
            "count": qs.count(),
        })


class PlayerDetailView(APIView):
    """GET /api/v1/sports/players/{id}/ — single player."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, id: uuid.UUID) -> Response:
        player = get_object_or_404(Player, id=id, is_active=True)
        return Response(PlayerDetailSerializer(player).data)
