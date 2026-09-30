"""
Preferences views.
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sports_platform.preferences.serializers import (
    BulkUpdatePreferencesSerializer,
    FollowEntitySerializer,
)
from sports_platform.preferences.services import PreferenceService


class UserPreferencesView(APIView):
    """
    GET: Retrieve current user's preferences.
    PUT: Bulk update sports & followed entities.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        data = PreferenceService.get_user_preferences(request.user)
        return Response(data, status=status.HTTP_200_OK)

    def put(self, request: Request) -> Response:
        serializer = BulkUpdatePreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        data = PreferenceService.bulk_update_preferences(
            user=request.user,
            sports_slugs=validated["sports"],
            following_data=validated.get("following", []),
        )
        return Response(data, status=status.HTTP_200_OK)


class FollowEntityView(APIView):
    """
    POST: Follow a specific entity (team, competition, country, player).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = FollowEntitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        result = PreferenceService.follow_entity(
            user=request.user,
            sport_slug=validated["sport"],
            entity_type=validated["entity_type"],
            entity_id=validated["entity_id"],
        )
        return Response(result, status=status.HTTP_201_CREATED)


class UnfollowEntityView(APIView):
    """
    DELETE: Unfollow a specific entity.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, entity_type: str, entity_id: str) -> Response:
        PreferenceService.unfollow_entity(
            user=request.user,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
