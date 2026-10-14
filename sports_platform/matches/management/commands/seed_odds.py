"""
Management command to seed realistic odds and movement history — Milestone 7.
Populates PostgreSQL (match_odds_current, match_odds_history) and Redis.
"""
from datetime import datetime, timedelta, timezone
import random
from django.core.management.base import BaseCommand

from sports_platform.matches.models import Match, MatchOddsCurrent, MatchOddsHistory
from sports_platform.matches.redis_store import get_match_store
from sports_platform.providers.odds_normalization import compute_odds_fingerprint


class Command(BaseCommand):
    help = "Seed realistic current and historical betting odds for matches"

    def handle(self, *args, **options):
        self.stdout.write("Seeding odds data for matches...")
        matches = Match.objects.all().select_related("home_team", "away_team", "sport")
        if not matches.exists():
            self.stdout.write(self.style.WARNING("No matches found. Run seed_sports first."))
            return

        store = get_match_store()
        seeded_count = 0
        now = datetime.now(timezone.utc)

        bookmakers = ["Bet365", "Pinnacle", "Betfair"]

        for match in matches:
            home_name = match.home_team.short_name or match.home_team.name
            away_name = match.away_team.short_name or match.away_team.name
            sport_slug = match.sport.slug

            # Base prices depending on sport
            if sport_slug == "football":
                base_home = round(random.uniform(1.60, 2.40), 2)
                base_draw = round(random.uniform(3.10, 3.80), 2)
                base_away = round(random.uniform(2.60, 4.20), 2)

                outcomes = [
                    {"outcome": "home_win", "display": home_name, "value": base_home},
                    {"outcome": "draw", "display": "Draw", "value": base_draw},
                    {"outcome": "away_win", "display": away_name, "value": base_away},
                ]
            else:
                # 2-way market for cricket or tennis
                base_home = round(random.uniform(1.45, 2.10), 2)
                base_away = round(random.uniform(1.75, 2.70), 2)
                outcomes = [
                    {"outcome": "home_win", "display": home_name, "value": base_home},
                    {"outcome": "away_win", "display": away_name, "value": base_away},
                ]

            # Generate 4-5 historical movement points over past 3 hours
            movements = []
            curr_home = base_home
            curr_away = base_away
            curr_draw = base_draw if sport_slug == "football" else None

            for i in range(4, -1, -1):
                t = now - timedelta(minutes=i * 25)
                # Slight shift
                shift_h = round(curr_home + random.uniform(-0.06, 0.06), 2)
                shift_a = round(curr_away + random.uniform(-0.06, 0.06), 2)
                m_entry = {
                    "at": t.isoformat(),
                    "home_win": shift_h,
                    "away_win": shift_a,
                }
                if curr_draw is not None:
                    shift_d = round(curr_draw + random.uniform(-0.05, 0.05), 2)
                    m_entry["draw"] = shift_d
                    curr_draw = shift_d
                movements.append(m_entry)
                curr_home = shift_h
                curr_away = shift_a

            # Final current outcomes
            if sport_slug == "football":
                current_outcomes = [
                    {"outcome": "home_win", "display": home_name, "value": curr_home},
                    {"outcome": "draw", "display": "Draw", "value": curr_draw},
                    {"outcome": "away_win", "display": away_name, "value": curr_away},
                ]
            else:
                current_outcomes = [
                    {"outcome": "home_win", "display": home_name, "value": curr_home},
                    {"outcome": "away_win", "display": away_name, "value": curr_away},
                ]

            bookmaker = bookmakers[seeded_count % len(bookmakers)]
            market_type = "match_winner"
            fingerprint = compute_odds_fingerprint(current_outcomes)

            odds_data = {
                "outcomes": current_outcomes,
                "movement": movements,
                "fingerprint": fingerprint,
            }

            # 1. Upsert Postgres MatchOddsCurrent
            MatchOddsCurrent.objects.update_or_create(
                match=match,
                provider_name="odds_provider_canonical",
                market_type=market_type,
                bookmaker=bookmaker,
                defaults={
                    "odds_data": odds_data,
                    "is_open": True,
                },
            )

            # 2. Add history points to MatchOddsHistory
            for m in movements:
                hist_outcomes = [
                    {"outcome": "home_win", "value": m["home_win"]},
                    {"outcome": "away_win", "value": m["away_win"]},
                ]
                if "draw" in m:
                    hist_outcomes.append({"outcome": "draw", "value": m["draw"]})

                dt = datetime.fromisoformat(m["at"])
                MatchOddsHistory.objects.update_or_create(
                    match=match,
                    provider_name="odds_provider_canonical",
                    market_type=market_type,
                    recorded_at=dt,
                    defaults={
                        "bookmaker": bookmaker,
                        "odds_data": {"outcomes": hist_outcomes},
                    },
                )

            # 3. Update Redis cache & pubsub
            try:
                store.update_odds(
                    match_id=str(match.id),
                    market_type=market_type,
                    provider="odds_provider_canonical",
                    bookmaker=bookmaker,
                    outcomes=current_outcomes,
                    movement=movements,
                    is_open=True,
                )
            except Exception as e:
                self.stdout.write(f"Redis odds cache error (non-fatal): {e}")

            seeded_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded odds for {seeded_count} matches!"))
