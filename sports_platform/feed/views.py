"""
Feed API views (Milestone 5).

Endpoints:
  GET /api/v1/feed — personalized match feed based on user preferences.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sports_platform.feed.serializers import FeedResponseSerializer
from sports_platform.feed.services import FeedService

logger = logging.getLogger(__name__)


class FeedView(APIView):
    """
    GET /api/v1/feed
    Returns personalized match feed based on user's followed sports and entities.

    Query params:
      status    — comma-separated statuses (e.g. 'live,upcoming' or 'live', 'upcoming', 'completed')
      cursor    — cursor for cursor-based pagination
      page_size — items per page (default 20, max 50)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        status_filter = request.query_params.get("status")
        cursor = request.query_params.get("cursor")

        try:
            page_size = int(request.query_params.get("page_size", 20))
        except (ValueError, TypeError):
            page_size = 20

        feed_data = FeedService.assemble_feed(
            user=request.user,
            status_filter=status_filter,
            cursor=cursor,
            page_size=page_size,
        )

        serializer = FeedResponseSerializer(feed_data)
        return Response(serializer.data, status=status.HTTP_200_OK)
