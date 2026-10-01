"""
Sports URL configuration.
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
    path("", SportListView.as_view(), name="sport-list"),
    path("countries/", CountryListView.as_view(), name="country-list"),
    path("<slug:slug>/", SportDetailView.as_view(), name="sport-detail"),
    path("<slug:slug>/teams/", TeamListView.as_view(), name="team-list"),
    path("<slug:slug>/competitions/", CompetitionListView.as_view(), name="competition-list"),
    path("<slug:slug>/players/", PlayerListView.as_view(), name="player-list"),
    path("teams/<uuid:id>/", TeamDetailView.as_view(), name="team-detail"),
    path("competitions/<uuid:id>/", CompetitionDetailView.as_view(), name="competition-detail"),
    path("players/<uuid:id>/", PlayerDetailView.as_view(), name="player-detail"),
]
