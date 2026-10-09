"""
Management command to seed realistic live and upcoming matches with scores and timeline events.
Populates both PostgreSQL and Redis live state store.
"""
from datetime import datetime, timedelta, timezone
import json
import logging
import time
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from sports_platform.matches.models import Match, MatchEvent, MatchScore, MatchStatus
from sports_platform.matches.redis_store import get_match_store
from sports_platform.sports.models import Competition, Country, Sport, Team

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Seeds initial sample live & upcoming matches, scores, and events into DB and Redis."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting matches seed...")

        football = Sport.objects.filter(slug="football").first()
        cricket = Sport.objects.filter(slug="cricket").first()

        if not football or not cricket:
            self.stdout.write(self.style.ERROR("Sports not found. Please run 'python manage.py seed_sports' first."))
            return

        gbr = Country.objects.filter(iso_code="GBR").first()
        esp = Country.objects.filter(iso_code="ESP").first()

        # Ensure teams
        arsenal, _ = Team.objects.get_or_create(
            name="Arsenal FC",
            defaults={"short_name": "ARS", "sport": football, "country": gbr, "team_type": "club"}
        )
        liverpool, _ = Team.objects.get_or_create(
            name="Liverpool FC",
            defaults={"short_name": "LIV", "sport": football, "country": gbr, "team_type": "club"}
        )
        rm, _ = Team.objects.get_or_create(
            name="Real Madrid",
            defaults={"short_name": "RMA", "sport": football, "country": esp, "team_type": "club"}
        )
        mci, _ = Team.objects.get_or_create(
            name="Manchester City",
            defaults={"short_name": "MCI", "sport": football, "country": gbr, "team_type": "club"}
        )
        chelsea = Team.objects.filter(name__icontains="Chelsea").first() or Team.objects.create(
            name="Chelsea FC", short_name="CHE", sport=football, country=gbr, team_type="club"
        )
        india = Team.objects.filter(name__icontains="India").first()
        australia = Team.objects.filter(name__icontains="Australia").first()

        premier_league = Competition.objects.filter(name__icontains="Premier League").first()
        ucl = Competition.objects.filter(name__icontains="Champions League").first() or premier_league
        cwc = Competition.objects.filter(sport=cricket).first()

        store = get_match_store()
        now = datetime.now(timezone.utc)

        # ── 1. Match 1: Arsenal vs Liverpool (Live Football) ──────────────────
        m1, _ = Match.objects.update_or_create(
            provider_match_id="sim_pl_ars_liv_01",
            defaults={
                "sport": football,
                "competition": premier_league,
                "home_team": arsenal,
                "away_team": liverpool,
                "scheduled_at": now - timedelta(minutes=70),
                "started_at": now - timedelta(minutes=68),
                "status": MatchStatus.LIVE,
                "venue": "Emirates Stadium, London",
                "round": "Matchday 28",
                "source_provider": "simulator",
                "metadata": {"attendance": 60200, "weather": "Clear, 12°C"},
            },
        )

        score_data_1 = {
            "home": 2,
            "away": 1,
            "period": "2H",
            "minute": "67'",
            "detail": "Emirates Stadium · London",
        }
        MatchScore.objects.update_or_create(
            match=m1,
            defaults={"score_data": score_data_1, "sequence_number": 12},
        )

        events_1 = [
            {"min": 31, "type": "goal", "desc": "GOAL · Arsenal — Martin Ødegaard · Assisted by Saka", "seq": 1},
            {"min": 45, "type": "period", "desc": "Half time — Arsenal 1 — 0 Liverpool", "seq": 2},
            {"min": 54, "type": "goal", "desc": "GOAL · Liverpool — Mohamed Salah · Assisted by Szoboszlai", "seq": 3},
            {"min": 61, "type": "substitution", "desc": "Substitution · Liverpool — Darwin Núñez for Luis Díaz", "seq": 4},
            {"min": 67, "type": "goal", "desc": "GOAL · Arsenal — Bukayo Saka · Right footed shot", "seq": 5},
        ]
        for e in events_1:
            MatchEvent.objects.update_or_create(
                match=m1,
                source_provider="simulator",
                event_sequence=e["seq"],
                defaults={
                    "sport": football,
                    "event_type": e["type"],
                    "minute": e["min"],
                    "description": e["desc"],
                    "team": arsenal if "Arsenal" in e["desc"] else liverpool,
                    "occurred_at": now - timedelta(minutes=70 - (e["seq"] * 10)),
                },
            )
            store.push_event(
                str(m1.id),
                e["seq"],
                {"event_type": e["type"], "minute": e["min"], "description": e["desc"]},
            )

        store.add_to_live(str(m1.id))
        store.update_score(
            match_id=str(m1.id),
            score_data=score_data_1,
            sequence_number=12,
            status="live",
        )
        self.stdout.write(self.style.SUCCESS(f"  ✓ Live: {arsenal.name} vs {liverpool.name}"))

        # ── 2. Match 2: India vs Australia (Live Cricket) ─────────────────────
        if india and australia and cwc:
            m2, _ = Match.objects.update_or_create(
                provider_match_id="sim_cwc_ind_aus_01",
                defaults={
                    "sport": cricket,
                    "competition": cwc,
                    "home_team": india,
                    "away_team": australia,
                    "scheduled_at": now - timedelta(hours=3),
                    "started_at": now - timedelta(hours=3),
                    "status": MatchStatus.LIVE,
                    "venue": "Narendra Modi Stadium, Ahmedabad",
                    "round": "Group Stage",
                    "source_provider": "simulator",
                    "metadata": {"toss": "Australia won toss and elected to bat"},
                },
            )

            score_data_2 = {
                "home": "241/4",
                "away": "289/7",
                "period": "2nd Innings",
                "minute": "32.4 OV",
                "detail": "India need 49 runs from 104 balls",
            }
            MatchScore.objects.update_or_create(
                match=m2,
                defaults={"score_data": score_data_2, "sequence_number": 45},
            )

            cricket_events = [
                {"min": 10, "type": "boundary", "desc": "FOUR · Travis Head drives through covers", "seq": 1},
                {"min": 18, "type": "wicket", "desc": "WICKET · Bumrah strikes! Head b Bumrah 42 (36)", "seq": 2},
                {"min": 25, "type": "six", "desc": "SIX · Glenn Maxwell clears long-on", "seq": 3},
                {"min": 50, "type": "period", "desc": "Innings Break · Australia 289/7 (50 OV)", "seq": 4},
                {"min": 65, "type": "boundary", "desc": "FOUR · Rohit Sharma pulls behind square", "seq": 5},
                {"min": 78, "type": "wicket", "desc": "WICKET · Starc removes Rohit 87 (76)", "seq": 6},
                {"min": 92, "type": "milestone", "desc": "50 up for Virat Kohli! 54* off 58 balls", "seq": 7},
            ]
            for ce in cricket_events:
                MatchEvent.objects.update_or_create(
                    match=m2,
                    source_provider="simulator",
                    event_sequence=ce["seq"],
                    defaults={
                        "sport": cricket,
                        "event_type": ce["type"],
                        "minute": ce["min"],
                        "description": ce["desc"],
                        "team": india if "Rohit" in ce["desc"] or "Kohli" in ce["desc"] else australia,
                        "occurred_at": now - timedelta(minutes=180 - (ce["seq"] * 15)),
                    },
                )
                store.push_event(
                    str(m2.id),
                    ce["seq"],
                    {"event_type": ce["type"], "minute": ce["min"], "description": ce["desc"]},
                )

            store.add_to_live(str(m2.id))
            store.update_score(
                match_id=str(m2.id),
                score_data=score_data_2,
                sequence_number=45,
                status="live",
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ Live: {india.name} vs {australia.name}"))

        # ── 3. Match 3: Real Madrid vs Man City (Upcoming Football) ───────────
        m3, _ = Match.objects.update_or_create(
            provider_match_id="sim_ucl_rma_mci_01",
            defaults={
                "sport": football,
                "competition": ucl,
                "home_team": rm,
                "away_team": mci,
                "scheduled_at": now + timedelta(hours=4),
                "status": MatchStatus.SCHEDULED,
                "venue": "Santiago Bernabéu, Madrid",
                "round": "Quarter-finals",
                "source_provider": "simulator",
                "metadata": {"detail": "Today · Santiago Bernabéu"},
            },
        )
        store.add_upcoming("football", str(m3.id), m3.scheduled_at)
        self.stdout.write(self.style.SUCCESS(f"  ✓ Upcoming: {rm.name} vs {mci.name}"))

        # ── 4. Match 4: Chelsea vs Arsenal (Upcoming Football) ────────────────
        m4, _ = Match.objects.update_or_create(
            provider_match_id="sim_pl_che_ars_01",
            defaults={
                "sport": football,
                "competition": premier_league,
                "home_team": chelsea,
                "away_team": arsenal,
                "scheduled_at": now + timedelta(days=2),
                "status": MatchStatus.SCHEDULED,
                "venue": "Stamford Bridge, London",
                "round": "Matchday 29",
                "source_provider": "simulator",
                "metadata": {"detail": "Sunday · 14:30 · Stamford Bridge"},
            },
        )
        store.add_upcoming("football", str(m4.id), m4.scheduled_at)
        self.stdout.write(self.style.SUCCESS(f"  ✓ Upcoming: {chelsea.name} vs {arsenal.name}"))

        self.stdout.write(self.style.SUCCESS("\nDone! Matches seeded into PostgreSQL and Redis successfully."))
