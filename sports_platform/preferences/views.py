"""
Preferences views.
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sports_platform.matches.models import Match
from sports_platform.preferences.models import NotificationLog, UserConsoleSession
from sports_platform.preferences.serializers import (
    BulkUpdatePreferencesSerializer,
    FollowEntitySerializer,
    NotificationLogSerializer,
    UpdateUserConsoleSessionSerializer,
    UserConsoleSessionSerializer,
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


class UserConsoleSessionView(APIView):
    """
    GET /api/v1/users/me/console/
    Retrieve current user's 3-match command console state.
    Auto-initializes with live/scheduled matches if empty.

    PUT /api/v1/users/me/console/
    Update pinned matches (up to 3), active match ID, and rotation settings.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        session, _ = UserConsoleSession.objects.get_or_create(user=request.user)

        # Auto-initialize with up to 4 live/scheduled matches if empty
        if not session.pinned_matches:
            top_matches = list(
                Match.objects.filter(status__in=["live", "scheduled"])
                .order_by("-status", "scheduled_at")[:4]
                .values_list("id", flat=True)
            )
            if top_matches:
                session.pinned_matches = [str(mid) for mid in top_matches]
                session.active_match_id = str(top_matches[0])
                session.save(update_fields=["pinned_matches", "active_match_id"])

        serializer = UserConsoleSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request: Request) -> Response:
        serializer = UpdateUserConsoleSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        session, _ = UserConsoleSession.objects.get_or_create(user=request.user)

        if "pinned_matches" in validated:
            session.pinned_matches = validated["pinned_matches"][:4]
        if "active_match_id" in validated:
            session.active_match_id = validated["active_match_id"]
        if "console_mode" in validated:
            session.console_mode = validated["console_mode"]
        if "rotation_angle" in validated:
            session.rotation_angle = validated["rotation_angle"]

        session.save()
        return Response(UserConsoleSessionSerializer(session).data, status=status.HTTP_200_OK)


class UserNotificationsView(APIView):
    """
    GET /api/v1/users/me/notifications/
    Returns list of notifications and unread count.
    Query param: unread_only (bool)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = NotificationLog.objects.filter(user=request.user)
        unread_only = request.query_params.get("unread_only", "false").lower() == "true"
        if unread_only:
            qs = qs.filter(is_read=False)

        total = qs.count()
        unread_count = NotificationLog.objects.filter(user=request.user, is_read=False).count()
        logs = qs[:50]

        return Response({
            "notifications": NotificationLogSerializer(logs, many=True).data,
            "unread_count": unread_count,
            "total": total,
        }, status=status.HTTP_200_OK)


class MarkNotificationReadView(APIView):
    """
    POST /api/v1/users/me/notifications/<uuid:id>/read/
    Mark a single notification as read.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, id: str) -> Response:
        try:
            notif = NotificationLog.objects.get(id=id, user=request.user)
            notif.is_read = True
            notif.save(update_fields=["is_read"])
            return Response({"success": True}, status=status.HTTP_200_OK)
        except NotificationLog.DoesNotExist:
            return Response({"error": "Notification not found"}, status=status.HTTP_404_NOT_FOUND)


class MarkAllNotificationsReadView(APIView):
    """
    POST /api/v1/users/me/notifications/mark-all-read/
    Mark all notifications for the user as read.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        updated = NotificationLog.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"marked_read": updated}, status=status.HTTP_200_OK)


class TriggerTestNotificationView(APIView):
    """
    POST /api/v1/users/me/notifications/test-event/
    Simulate a real-time event for a background match to test the notification radar.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        notif_type = request.data.get("type", "goal")
        title = request.data.get("title", "⚡ GOAL in Background Match!")
        message = request.data.get(
            "message",
            "Real Madrid scored against Man City (74')! Current score: RMA 2 — 1 MCI",
        )
        match_id = request.data.get("match_id", None)
        extra_data = request.data.get("data", {
            "score": "2 - 1",
            "minute": "74'",
            "team": "Real Madrid",
            "is_background": True,
        })

        notif = NotificationLog.objects.create(
            user=request.user,
            match_id=match_id if match_id and len(str(match_id)) > 10 else None,
            notification_type=notif_type,
            title=title,
            message=message,
            data=extra_data,
            channel="websocket",
            is_read=False,
        )

        # Also publish to Redis user websocket channel if available
        try:
            import json
            from sports_platform.matches.redis_store import get_match_store
            store = get_match_store()
            pub_payload = json.dumps({
                "type": "notification",
                "notification": NotificationLogSerializer(notif).data,
            })
            store._redis.publish(f"ws:user:{request.user.id}", pub_payload)
        except Exception:
            pass

        return Response(NotificationLogSerializer(notif).data, status=status.HTTP_201_CREATED)
