"""
simulate_live_match management command.

Simulates a complete live match lifecycle for local development/testing
WITHOUT any real provider API calls.

Publishes the full event sequence to Kafka:
  match.discovered → score.updated (every 15s) → match.event (goals/cards)
  → match.started → match.completed

Usage:
    python manage.py simulate_live_match --sport football
    python manage.py simulate_live_match --sport football --duration 60
"""
import time
import uuid
from datetime import datetime, timezone

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Simulate a live match for local testing (no real API calls)."

    def add_arguments(self, parser):
        parser.add_argument("--sport", default="football")
        parser.add_argument("--duration", type=int, default=30, help="Simulation duration in seconds")
        parser.add_argument("--dry-run", action="store_true", help="Print events without publishing to Kafka")

    def handle(self, *args, **options):
        sport = options["sport"]
        duration = options["duration"]
        dry_run = options["dry_run"]

        from sports_platform.kafka.events import (
            MatchDiscoveredEvent, MatchStartedEvent, ScoreUpdatedEvent,
            MatchEventPublished, MatchCompletedEvent,
        )
        from sports_platform.kafka.producer import get_producer

        match_id = str(uuid.uuid4())
        internal_match_id = str(uuid.uuid4())
        provider_name = "simulator"

        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(f"  Simulating live {sport} match")
        self.stdout.write(f"  provider_match_id: {match_id}")
        self.stdout.write(f"  internal_match_id: {internal_match_id}")
        self.stdout.write(f"  duration: {duration}s  dry_run: {dry_run}")
        self.stdout.write(f"{'=' * 60}\n")

        producer = None if dry_run else get_producer()

        def publish(topic, event):
            self.stdout.write(
                f"  [{event.event_type}] {event.model_dump_json(exclude={'event_id', 'occurred_at', 'schema_version'})}"
            )
            if not dry_run:
                producer.publish(topic, event)

        from sports_platform.kafka.events import KafkaTopics

        # ── 1. Match discovered ───────────────────────────────────────────────
        discovered = MatchDiscoveredEvent(
            provider_name=provider_name,
            provider_match_id=match_id,
            sport=sport,
            competition_name="Simulated League",
            competition_provider_id="sim-comp-1",
            home_team_name="Team Alpha",
            home_team_provider_id="sim-team-1",
            away_team_name="Team Beta",
            away_team_provider_id="sim-team-2",
            scheduled_at=datetime.now(tz=timezone.utc),
            status="scheduled",
            venue="Simulation Stadium",
        )
        publish(KafkaTopics.MATCH_DISCOVERED, discovered)
        time.sleep(1)

        # ── 2. Match started ──────────────────────────────────────────────────
        started = MatchStartedEvent(
            provider_name=provider_name,
            provider_match_id=match_id,
            sport=sport,
            internal_match_id=internal_match_id,
        )
        publish(KafkaTopics.MATCH_STARTED, started)

        # ── 3. Live score + event simulation loop ─────────────────────────────
        home_score = 0
        away_score = 0
        event_seq = 0
        score_seq = 0
        interval = max(duration // 10, 2)
        elapsed = 0

        self.stdout.write(f"\n  --- Match in progress ({duration}s simulation) ---")
        while elapsed < duration:
            time.sleep(interval)
            elapsed += interval
            minute = int((elapsed / duration) * 90)
            score_seq += 1

            # Randomly score a goal every ~3 ticks
            if elapsed % (interval * 3) == 0:
                home_score += 1
                event_seq += 1
                goal_event = MatchEventPublished(
                    provider_name=provider_name,
                    provider_match_id=match_id,
                    internal_match_id=internal_match_id,
                    sport=sport,
                    event_type_detail="goal",
                    event_sequence=event_seq,
                    minute=minute,
                    player_name="Alpha Striker",
                    description=f"Goal! {home_score}-{away_score} (min {minute})",
                )
                publish(KafkaTopics.MATCH_EVENT, goal_event)

            score_event = ScoreUpdatedEvent(
                provider_name=provider_name,
                provider_match_id=match_id,
                internal_match_id=internal_match_id,
                sport=sport,
                score_data={"home": home_score, "away": away_score, "minute": minute},
                sequence_number=score_seq,
                source_timestamp=datetime.now(tz=timezone.utc),
            )
            publish(KafkaTopics.SCORE_UPDATED, score_event)

        # ── 4. Match completed ────────────────────────────────────────────────
        completed = MatchCompletedEvent(
            provider_name=provider_name,
            provider_match_id=match_id,
            sport=sport,
            internal_match_id=internal_match_id,
            final_score_data={"home": home_score, "away": away_score},
        )
        publish(KafkaTopics.MATCH_COMPLETED, completed)

        if not dry_run:
            producer.flush()

        self.stdout.write(self.style.SUCCESS(
            f"\nSimulation complete. Final: Team Alpha {home_score} - {away_score} Team Beta"
        ))
