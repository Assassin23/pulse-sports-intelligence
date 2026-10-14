import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0001_initial"),
        ("preferences", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserConsoleSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "pinned_matches",
                    models.JSONField(
                        default=list,
                        help_text="Ordered list of up to 4 match UUID strings pinned to console slots.",
                    ),
                ),
                ("active_match_id", models.CharField(blank=True, default="", max_length=64)),
                (
                    "console_mode",
                    models.CharField(
                        choices=[("circular", "Circular Dial"), ("triangular", "Triangular Hub")],
                        default="circular",
                        max_length=20,
                    ),
                ),
                ("rotation_angle", models.IntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="console_session",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "user_console_sessions",
            },
        ),
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("notification_type", models.CharField(db_index=True, max_length=50)),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField()),
                ("data", models.JSONField(default=dict)),
                (
                    "channel",
                    models.CharField(
                        choices=[("websocket", "WebSocket"), ("push", "Push"), ("both", "Both")],
                        default="websocket",
                        max_length=20,
                    ),
                ),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "match",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notification_logs",
                        to="matches.match",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "notification_log",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["user", "is_read"], name="notif_log_user_is_read_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["user", "created_at"], name="notif_log_user_created_idx"),
        ),
    ]
