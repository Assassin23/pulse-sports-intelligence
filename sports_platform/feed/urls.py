"""
Feed URL configuration.
"""
from django.urls import re_path

from sports_platform.feed.views import FeedView

app_name = "feed"

urlpatterns = [
    re_path(r"^$", FeedView.as_view(), name="user-feed"),
]
