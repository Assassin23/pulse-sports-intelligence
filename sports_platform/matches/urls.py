"""
Matches URL configuration.
"""
from django.urls import path

from sports_platform.matches.views import (
    LiveMatchesView,
    MatchDetailView,
    MatchEventsView,
    MatchOddsView,
    UpcomingMatchesView,
)

app_name = "matches"

urlpatterns = [
    path("upcoming/", UpcomingMatchesView.as_view(), name="matches-upcoming"),
    path("live/", LiveMatchesView.as_view(), name="matches-live"),
    path("<uuid:id>/", MatchDetailView.as_view(), name="match-detail"),
    path("<uuid:id>/events/", MatchEventsView.as_view(), name="match-events"),
    path("<uuid:id>/odds/", MatchOddsView.as_view(), name="match-odds"),
]
