import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MatchOddsCurrent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("provider_name", models.CharField(db_index=True, max_length=100)),
                ("market_type", models.CharField(db_index=True, max_length=50)),
                ("bookmaker", models.CharField(max_length=100)),
                ("odds_data", models.JSONField(default=dict)),
                ("is_open", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "match",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="odds_current",
                        to="matches.match",
                    ),
                ),
            ],
            options={
                "db_table": "match_odds_current",
                "unique_together": {("match", "provider_name", "market_type", "bookmaker")},
            },
        ),
        migrations.CreateModel(
            name="MatchOddsHistory",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("provider_name", models.CharField(db_index=True, max_length=100)),
                ("market_type", models.CharField(db_index=True, max_length=50)),
                ("bookmaker", models.CharField(max_length=100)),
                ("odds_data", models.JSONField(default=dict)),
                ("recorded_at", models.DateTimeField(db_index=True)),
                (
                    "match",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="odds_history",
                        to="matches.match",
                    ),
                ),
            ],
            options={
                "db_table": "match_odds_history",
                "ordering": ["recorded_at"],
                "unique_together": {("match", "provider_name", "market_type", "recorded_at")},
            },
        ),
        migrations.AddIndex(
            model_name="matchoddscurrent",
            index=models.Index(fields=["match", "market_type"], name="idx_odds_curr_match_mkt"),
        ),
        migrations.AddIndex(
            model_name="matchoddshistory",
            index=models.Index(
                fields=["match", "market_type", "recorded_at"],
                name="idx_odds_hist_match_mkt_time",
            ),
        ),
    ]
