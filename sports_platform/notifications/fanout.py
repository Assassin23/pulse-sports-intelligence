"""
Notification fanout and user targeting service — Milestone 8.

Queries user_followed_entities, user_notification_preferences, and active
user_console_sessions to dispatch real-time alerts. Specifically identifies
events occurring in "background matches" (matches not currently in the user's
3-match command console) to trigger non-intrusive radar notifications.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from django.db import connection

from sports_platform.matches.redis_store import get_match_store
from sports_platform.preferences.models import NotificationLog, UserConsoleSession

logger = logging.getLogger(__name__)


def should_send_notification(user_id: str, match_id: str, notif_type: str) -> bool:
    """Allow max 3 notifications of same type per match per 5 minutes."""
    try:
        store = get_match_store()
        key = f"notif:rl:{user_id}:{match_id}:{notif_type}"
        count = store._redis.incr(key)
        if count == 1:
            store._redis.expire(key, 300)
        return count <= 3
    except Exception:
        return True


class NotificationFanout:
    """
    Find users to notify for a match event and dispatch notifications.
    """

    def get_users_to_notify(
        self, match: Dict[str, Any], notification_type: str
    ) -> List[Dict[str, Any]]:
        """
        1. Find entity IDs related to match (home_team, away_team, competition).
        2. Query user_followed_entities for users following any of these.
        3. Match with user_notification_preferences.
        """
        relevant_entity_ids = []
        if match.get("home_team_id"):
            relevant_entity_ids.append(str(match["home_team_id"]))
        if match.get("away_team_id"):
            relevant_entity_ids.append(str(match["away_team_id"]))
        if match.get("competition_id"):
            relevant_entity_ids.append(str(match["competition_id"]))

        if not relevant_entity_ids:
            return []

        query = """
            SELECT DISTINCT ufe.user_id, unp.channel_websocket, unp.channel_push
            FROM user_followed_entities ufe
            LEFT JOIN user_notification_preferences unp
                ON unp.user_id = ufe.user_id
                AND unp.sport_id = ufe.sport_id
                AND unp.notification_type = %s
            WHERE ufe.entity_id = ANY(%s::uuid[])
              AND (unp.is_enabled IS NULL OR unp.is_enabled = TRUE)
        """

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, [notification_type, relevant_entity_ids])
                return [
                    {
                        "user_id": str(row[0]),
                        "channel_websocket": row[1] if row[1] is not None else True,
                        "channel_push": row[2] if row[2] is not None else True,
                    }
                    for row in cursor.fetchall()
                ]
        except Exception as exc:
            logger.warning("Notification fanout query failed", extra={"error": str(exc)})
            return []

    def dispatch_match_event_notifications(
        self,
        match: Dict[str, Any],
        event_type: str,
        title: str,
        message: str,
        event_data: Dict[str, Any],
    ) -> int:
        """
        Fan-out notification to all interested users.
        Checks if the match is in the user's active 3-slot console or background.
        """
        users = self.get_users_to_notify(match, event_type)
        if not users:
            return 0

        match_id = str(match["id"])
        delivered_count = 0
        store = get_match_store()

        # Batch lookup console sessions for these users to identify background matches
        user_ids = [u["user_id"] for u in users]
        sessions = {
            str(s.user_id): s.pinned_matches
            for s in UserConsoleSession.objects.filter(user_id__in=user_ids)
        }

        for user_info in users:
            uid = user_info["user_id"]
            if not should_send_notification(uid, match_id, event_type):
                continue

            user_pinned = sessions.get(uid, [])
            is_background = match_id not in user_pinned

            payload_data = dict(event_data)
            payload_data.update({
                "match_id": match_id,
                "is_background": is_background,
                "home_team": match.get("home_team_name", ""),
                "away_team": match.get("away_team_name", ""),
            })

            notif_log = NotificationLog.objects.create(
                user_id=uid,
                match_id=match["id"],
                notification_type=event_type,
                title=title,
                message=message,
                data=payload_data,
                channel="websocket" if user_info["channel_websocket"] else "push",
                is_read=False,
            )

            # Publish to user's personal WebSocket stream
            if user_info["channel_websocket"]:
                try:
                    pub_payload = json.dumps({
                        "type": "notification",
                        "notification": {
                            "id": str(notif_log.id),
                            "match_id": match_id,
                            "notification_type": event_type,
                            "title": title,
                            "message": message,
                            "data": payload_data,
                            "is_read": False,
                            "created_at": notif_log.created_at.isoformat(),
                        },
                    })
                    store._redis.publish(f"ws:user:{uid}", pub_payload)
                except Exception as exc:
                    logger.warning("Failed to publish to ws:user channel", extra={"error": str(exc)})

            delivered_count += 1

        return delivered_count
