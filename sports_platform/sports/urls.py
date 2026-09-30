"""
Sports URL patterns.
"""
from django.urls import path

from sports_platform.sports.views import (
    CompetitionDetailView,
    CompetitionListView,
    CountryListView,
    PlayerDetailView,
    PlayerListView,
    SportDetailView,
    SportListView,
    TeamDetailView,
    TeamListView,
)

app_name = "sports"

urlpatterns = [
    # Sports catalog
    path("", SportListView.as_view(), name="sport-list"),
    path("<slug:slug>/", SportDetailView.as_view(), name="sport-detail"),
    # Countries
    path("countries/", CountryListView.as_view(), name="country-list"),
    # Teams
    path("<slug:slug>/teams/", TeamListView.as_view(), name="team-list"),
    path("teams/<uuid:id>/", TeamDetailView.as_view(), name="team-detail"),
    # Competitions
    path("<slug:slug>/competitions/", CompetitionListView.as_view(), name="competition-list"),
    path("competitions/<uuid:id>/", CompetitionDetailView.as_view(), name="competition-detail"),
    # Players
    path("<slug:slug>/players/", PlayerListView.as_view(), name="player-list"),
    path("players/<uuid:id>/", PlayerDetailView.as_view(), name="player-detail"),
]
