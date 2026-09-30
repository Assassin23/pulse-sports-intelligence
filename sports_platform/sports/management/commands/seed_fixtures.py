"""
seed_fixtures management command.

Pulls upcoming fixtures from configured providers and stores
them via EntityMappingService dedup logic.

Usage:
    python manage.py seed_fixtures --sport football --days 3
"""
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sports_platform.providers.mapping_service import EntityMappingService
from sports_platform.providers.registry import get_registry
from sports_platform.sports.models import Country, Sport

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Seed upcoming fixture data from configured sports data providers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sport",
            type=str,
            default=None,
            help="Sport slug to fetch fixtures for (e.g., 'football'). Defaults to all registered sports.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="Number of days ahead to fetch fixtures for (default: 3).",
        )

    def handle(self, *args, **options):
        sport_slug = options.get("sport")
        days_ahead = options.get("days", 3)
        registry = get_registry()

        # Determine which sports to process
        if sport_slug:
            sports_to_process = [sport_slug]
        else:
            sports_to_process = list(registry._sport_to_providers.keys())

        if not sports_to_process:
            self.stdout.write(
                self.style.WARNING(
                    "No providers registered. Configure API keys in your .env and restart."
                )
            )
            return

        self.stdout.write(f"Seeding fixtures for sports: {sports_to_process}, {days_ahead} days ahead.")

        for s_slug in sports_to_process:
            try:
                sport = Sport.objects.get(slug=s_slug, is_active=True)
            except Sport.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"Sport '{s_slug}' not found in DB — run seed_sports first.")
                )
                continue

            try:
                provider = registry.get_primary_provider(s_slug)
            except ValueError as e:
                self.stdout.write(self.style.WARNING(str(e)))
                continue

            self.stdout.write(f"  Fetching from provider: {provider.provider_name}")
            try:
                fixtures = provider.fetch_upcoming_fixtures(s_slug, days_ahead=days_ahead)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"  Provider error for {provider.provider_name}/{s_slug}: {e}"
                    )
                )
                continue

            self.stdout.write(f"  Found {len(fixtures)} fixtures. Processing...")
            saved = 0
            skipped = 0
            for fixture in fixtures:
                try:
                    with transaction.atomic():
                        # Upsert competition
                        comp = EntityMappingService.upsert_competition(
                            provider_name=provider.provider_name,
                            provider_competition_id=fixture.competition_provider_id,
                            sport=sport,
                            competition_name=fixture.competition_name,
                            season=fixture.season or "",
                        )
                        # Upsert home team
                        home_team = EntityMappingService.upsert_team(
                            provider_name=provider.provider_name,
                            provider_team_id=fixture.home_team_provider_id,
                            sport=sport,
                            team_name=fixture.home_team_name,
                        )
                        # Upsert away team
                        away_team = EntityMappingService.upsert_team(
                            provider_name=provider.provider_name,
                            provider_team_id=fixture.away_team_provider_id,
                            sport=sport,
                            team_name=fixture.away_team_name,
                        )
                    saved += 1
                except Exception as e:
                    skipped += 1
                    logger.warning(
                        "Fixture upsert failed",
                        extra={
                            "provider_match_id": fixture.provider_match_id,
                            "error": str(e),
                        },
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  Done: {saved} fixtures saved, {skipped} skipped."
                )
            )

        self.stdout.write(self.style.SUCCESS("seed_fixtures complete."))
