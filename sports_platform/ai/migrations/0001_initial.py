from django.conf import settings
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("matches", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIConversation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "match",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_conversations",
                        to="matches.match",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "ai_conversations",
                "ordering": ["-updated_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "match"],
                        name="idx_ai_conv_user_match",
                    ),
                    models.Index(
                        fields=["updated_at"],
                        name="idx_ai_conv_updated",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="AIMessage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("assistant", "Assistant"),
                            ("system", "System"),
                        ],
                        max_length=20,
                    ),
                ),
                ("content", models.TextField()),
                ("tool_calls", models.JSONField(blank=True, default=list)),
                ("sources", models.JSONField(blank=True, default=list)),
                ("token_usage", models.JSONField(blank=True, default=dict)),
                ("latency_ms", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="ai.aiconversation",
                    ),
                ),
            ],
            options={
                "db_table": "ai_messages",
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(
                        fields=["conversation", "created_at"],
                        name="idx_ai_msg_conv_time",
                    ),
                ],
            },
        ),
    ]
