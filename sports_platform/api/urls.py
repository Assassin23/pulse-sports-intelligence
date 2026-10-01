"""
API-level URL configuration.
All routes under /api/v1/
"""
from django.urls import include, path

app_name = "api-v1"

urlpatterns = [
    path("auth/", include("sports_platform.users.urls.auth", namespace="auth")),
    path("users/", include("sports_platform.users.urls.users", namespace="users")),
    path("sports/", include("sports_platform.sports.urls", namespace="sports")),
    path("matches/", include("sports_platform.matches.urls", namespace="matches")),
]
