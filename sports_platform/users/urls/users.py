"""User URL patterns."""
from django.urls import path

from sports_platform.users.views.user_views import (
    ChangePasswordView,
    DeleteAccountView,
    MeView,
)
from sports_platform.preferences.views import (
    FollowEntityView,
    MarkAllNotificationsReadView,
    MarkNotificationReadView,
    TriggerTestNotificationView,
    UnfollowEntityView,
    UserConsoleSessionView,
    UserNotificationsView,
    UserPreferencesView,
)

app_name = "users"

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("me/delete/", DeleteAccountView.as_view(), name="delete-account"),
    # Preferences
    path("me/preferences/", UserPreferencesView.as_view(), name="preferences"),
    path("me/preferences/follow/", FollowEntityView.as_view(), name="follow"),
    path(
        "me/preferences/follow/<str:entity_type>/<uuid:entity_id>/",
        UnfollowEntityView.as_view(),
        name="unfollow",
    ),
    # User Console Session (Milestone 8)
    path("me/console/", UserConsoleSessionView.as_view(), name="console-session"),
    # Notifications (Milestone 8)
    path("me/notifications/", UserNotificationsView.as_view(), name="notifications"),
    path(
        "me/notifications/<uuid:id>/read/",
        MarkNotificationReadView.as_view(),
        name="notification-read",
    ),
    path(
        "me/notifications/mark-all-read/",
        MarkAllNotificationsReadView.as_view(),
        name="notifications-mark-all-read",
    ),
    path(
        "me/notifications/test-event/",
        TriggerTestNotificationView.as_view(),
        name="notification-test-event",
    ),
]
