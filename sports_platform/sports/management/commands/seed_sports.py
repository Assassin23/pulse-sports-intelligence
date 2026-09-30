"""
Management command to seed initial sports, countries, competitions, and teams reference data.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from sports_platform.sports.models import Competition, Country, Player, Sport, Team


class Command(BaseCommand):
    help = "Seeds reference data for sports, countries, competitions, and teams."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting sports seed...")

        # 1. Sports
        sports_data = [
            {"slug": "cricket", "name": "Cricket", "icon_url": "https://cdn.example.com/icons/cricket.svg"},
            {"slug": "football", "name": "Football", "icon_url": "https://cdn.example.com/icons/football.svg"},
            {"slug": "tennis", "name": "Tennis", "icon_url": "https://cdn.example.com/icons/tennis.svg"},
            {"slug": "basketball", "name": "Basketball", "icon_url": "https://cdn.example.com/icons/basketball.svg"},
            {"slug": "formula1", "name": "Formula 1", "icon_url": "https://cdn.example.com/icons/f1.svg"},
        ]
        sports = {}
        for item in sports_data:
            s, created = Sport.objects.update_or_create(
                slug=item["slug"],
                defaults={"name": item["name"], "icon_url": item["icon_url"], "is_active": True},
            )
            sports[item["slug"]] = s
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Sport: {s.name}")

        # 2. Countries
        countries_data = [
            {"iso_code": "IND", "name": "India"},
            {"iso_code": "AUS", "name": "Australia"},
            {"iso_code": "GBR", "name": "United Kingdom"},
            {"iso_code": "ESP", "name": "Spain"},
            {"iso_code": "USA", "name": "United States"},
            {"iso_code": "GER", "name": "Germany"},
            {"iso_code": "FRA", "name": "France"},
            {"iso_code": "NZL", "name": "New Zealand"},
            {"iso_code": "ZAF", "name": "South Africa"},
        ]
        countries = {}
        for item in countries_data:
            c, created = Country.objects.update_or_create(
                iso_code=item["iso_code"],
                defaults={"name": item["name"]},
            )
            countries[item["iso_code"]] = c
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Country: {c.name}")

        # 3. Competitions
        competitions_data = [
            {
                "sport": sports["cricket"],
                "country": countries["IND"],
                "name": "Indian Premier League",
                "short_name": "IPL",
                "season": "2026",
                "competition_type": "league",
            },
            {
                "sport": sports["cricket"],
                "country": None,
                "name": "ICC Men's T20 World Cup",
                "short_name": "T20 WC",
                "season": "2026",
                "competition_type": "international",
            },
            {
                "sport": sports["football"],
                "country": countries["GBR"],
                "name": "Premier League",
                "short_name": "EPL",
                "season": "2025-26",
                "competition_type": "league",
            },
            {
                "sport": sports["football"],
                "country": countries["ESP"],
                "name": "La Liga",
                "short_name": "La Liga",
                "season": "2025-26",
                "competition_type": "league",
            },
            {
                "sport": sports["football"],
                "country": None,
                "name": "UEFA Champions League",
                "short_name": "UCL",
                "season": "2025-26",
                "competition_type": "cup",
            },
        ]
        comps = {}
        for item in competitions_data:
            c, created = Competition.objects.update_or_create(
                sport=item["sport"],
                name=item["name"],
                defaults={
                    "country": item["country"],
                    "short_name": item["short_name"],
                    "season": item["season"],
                    "competition_type": item["competition_type"],
                    "is_active": True,
                },
            )
            comps[item["name"]] = c
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Competition: {c.name}")

        # 4. Teams
        teams_data = [
            {
                "sport": sports["cricket"],
                "country": countries["IND"],
                "name": "Royal Challengers Bengaluru",
                "short_name": "RCB",
                "team_type": "club",
            },
            {
                "sport": sports["cricket"],
                "country": countries["IND"],
                "name": "Chennai Super Kings",
                "short_name": "CSK",
                "team_type": "club",
            },
            {
                "sport": sports["cricket"],
                "country": countries["IND"],
                "name": "India National Cricket Team",
                "short_name": "India",
                "team_type": "national",
            },
            {
                "sport": sports["cricket"],
                "country": countries["AUS"],
                "name": "Australia National Cricket Team",
                "short_name": "Australia",
                "team_type": "national",
            },
            {
                "sport": sports["football"],
                "country": countries["GBR"],
                "name": "Chelsea FC",
                "short_name": "Chelsea",
                "team_type": "club",
            },
            {
                "sport": sports["football"],
                "country": countries["GBR"],
                "name": "Manchester United",
                "short_name": "Man Utd",
                "team_type": "club",
            },
            {
                "sport": sports["football"],
                "country": countries["ESP"],
                "name": "FC Barcelona",
                "short_name": "Barcelona",
                "team_type": "club",
            },
            {
                "sport": sports["football"],
                "country": countries["GBR"],
                "name": "England National Football Team",
                "short_name": "England",
                "team_type": "national",
            },
        ]
        for item in teams_data:
            t, created = Team.objects.update_or_create(
                sport=item["sport"],
                name=item["name"],
                defaults={
                    "country": item["country"],
                    "short_name": item["short_name"],
                    "team_type": item["team_type"],
                    "is_active": True,
                },
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Team: {t.name}")

        # 5. Players
        players_data = [
            {
                "sport": sports["cricket"],
                "nationality": countries["IND"],
                "name": "Virat Kohli",
                "position": "Batsman",
            },
            {
                "sport": sports["cricket"],
                "nationality": countries["IND"],
                "name": "Rohit Sharma",
                "position": "Batsman",
            },
            {
                "sport": sports["football"],
                "nationality": countries["ESP"],
                "name": "Lamine Yamal",
                "position": "Forward",
            },
            {
                "sport": sports["football"],
                "nationality": countries["GBR"],
                "name": "Cole Palmer",
                "position": "Attacking Midfielder",
            },
        ]
        for item in players_data:
            p, created = Player.objects.update_or_create(
                sport=item["sport"],
                name=item["name"],
                defaults={
                    "nationality": item["nationality"],
                    "position": item["position"],
                    "is_active": True,
                },
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Player: {p.name}")

        self.stdout.write(self.style.SUCCESS("Sports reference data seeded successfully!"))
