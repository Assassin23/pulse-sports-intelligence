# 13. Notifications

## 13.1 Notification Types & Triggers

| Notification Type | Trigger Event | Priority | Default Channels |
|---|---|---|---|
| `match_starting` | Match starts within 15 minutes | High | WebSocket + Push |
| `match_started` | `sports.match.started` | High | WebSocket + Push |
| `goal` | Match event type = `goal` | High | WebSocket + Push |
| `wicket` | Match event type = `wicket` | High | WebSocket + Push |
| `red_card` | Match event type = `red_card` | Medium | WebSocket + Push |
| `yellow_card` | Match event type = `yellow_card` | Low | WebSocket only |
| `half_time` | Match status → `half_time` | Medium | WebSocket |
| `match_completed` | `sports.match.completed` | High | WebSocket + Push |
| `major_milestone` | Century, hat-trick, penalty shootout | High | WebSocket + Push |

---

## 13.2 Notification Pipeline

```
sports.match.event / sports.match.started / sports.match.completed (Kafka)
          │
          ▼
Notification Processor (Kafka consumer)
          │
          │  1. Determines notification type from event
          │  2. Queries user_followed_entities table:
          │     "Which users follow this match's teams/competition/sport?"
          │  3. For each matched user:
          │     a. Check user_notification_preferences (is type enabled? which channels?)
          │     b. Check rate limit (max 10 notifications/match/user)
          │     c. Build notification payload
          │     d. Publish notifications.requested to Kafka (partitioned by user_id)
          ▼
Kafka: notifications.requested
          │
          ▼
Notification Delivery Worker (Celery consumer)
          │
          ├── WebSocket channel:
          │     PUBLISH ws:user:{user_id} notification_json
          │     (FastAPI gateway receives and delivers to connected WebSocket)
          │
          └── Push channel:
                Celery task: send_push_notification.delay(user_id, payload)
                  → Firebase Cloud Messaging (FCM) for Android/Web Push
                  → Apple Push Notification Service (APNs) for iOS
```

---

## 13.3 Affected Users Lookup (Efficient Fan-Out)

```python
# sports_platform/notifications/fanout.py

class NotificationFanout:
    """
    Efficiently find users to notify for a match event.
    
    Query strategy:
    1. Find all entities related to the match: home_team_id, away_team_id,
       competition_id, home_country_id, away_country_id
    2. Find users following ANY of those entities
    3. Filter by notification preferences
    """

    def get_users_to_notify(
        self, match: dict, notification_type: str
    ) -> list[dict]:
        from django.db import connection

        # All entity IDs relevant to this match
        relevant_entity_ids = [
            match["home_team_id"],
            match["away_team_id"],
            match["competition_id"],
        ]
        if match.get("home_country_id"):
            relevant_entity_ids.append(match["home_country_id"])
        if match.get("away_country_id"):
            relevant_entity_ids.append(match["away_country_id"])

        # Single optimized query: users following + notification prefs
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

        with connection.cursor() as cursor:
            cursor.execute(query, [notification_type, relevant_entity_ids])
            return [
                {
                    "user_id": row[0],
                    "channel_websocket": row[1] if row[1] is not None else True,
                    "channel_push": row[2] if row[2] is not None else True,
                }
                for row in cursor.fetchall()
            ]
```

---

## 13.4 Upcoming Match Reminder

Pre-match notifications (match starts in 15 minutes) are handled by Celery Beat:

```python
# sports_platform/notifications/tasks.py

from celery import shared_task

@shared_task
def schedule_match_start_reminders():
    """
    Runs every 5 minutes (Celery Beat schedule).
    Finds matches starting in the next 15-20 minute window.
    Schedules eta-based notification tasks.
    """
    from django.utils import timezone
    from sports_platform.matches.models import Match

    window_start = timezone.now() + timedelta(minutes=14)
    window_end = timezone.now() + timedelta(minutes=20)

    upcoming = Match.objects.filter(
        status="scheduled",
        scheduled_at__range=(window_start, window_end),
    ).select_related("home_team", "away_team", "competition")

    for match in upcoming:
        # Avoid duplicate reminders (check Redis flag)
        reminder_key = f"notif:reminder_sent:{match.id}"
        if redis_client.exists(reminder_key):
            continue

        fanout = NotificationFanout()
        users = fanout.get_users_to_notify(match.to_dict(), "match_starting")

        for user_info in users:
            send_match_starting_notification.apply_async(
                args=[user_info["user_id"], match.id],
                countdown=0,
            )

        redis_client.setex(reminder_key, 3600, "1")  # Don't resend for 1h
```

---

## 13.5 Push Notification Delivery

```python
# sports_platform/notifications/push/fcm.py

import httpx

class FCMPushProvider:
    """Firebase Cloud Messaging for Android + Web Push."""
    
    FCM_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    
    def __init__(self, project_id: str, service_account_key: dict):
        self._project_id = project_id
        self._access_token = self._get_access_token(service_account_key)

    def send(self, device_token: str, title: str, body: str, data: dict):
        payload = {
            "message": {
                "token": device_token,
                "notification": {"title": title, "body": body},
                "data": {k: str(v) for k, v in data.items()},
                "android": {"priority": "high"},
                "apns": {
                    "headers": {"apns-priority": "10"},
                    "payload": {"aps": {"alert": {"title": title, "body": body}}}
                }
            }
        }
        
        resp = httpx.post(
            self.FCM_URL.format(project_id=self._project_id),
            json=payload,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        resp.raise_for_status()
```

---

## 13.6 Notification Rate Limiting

To avoid notification spam during high-activity matches (e.g., multiple goals in quick succession):

```python
# Per-user, per-match notification rate limiter

def should_send_notification(user_id: str, match_id: str, notif_type: str) -> bool:
    """Allow max 3 notifications of same type per match per 5 minutes."""
    key = f"notif:rl:{user_id}:{match_id}:{notif_type}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 300)  # 5 minute window
    return count <= 3
```

---

## 13.7 Notification Log & Delivery Status

All sent notifications are written to `notification_log` table for:
- Debugging delivery issues
- User notification history endpoint
- Metric tracking (notifications sent per day, per type)
