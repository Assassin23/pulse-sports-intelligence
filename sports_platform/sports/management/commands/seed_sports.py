"""
Management command to seed initial sports, countries, competitions, teams, competition rosters, and players.
Focuses on the 3 foundational sports: Cricket, Football, and Tennis.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from sports_platform.sports.models import (
    Competition,
    CompetitionTeam,
    Country,
    Player,
    Sport,
    Team,
)


class Command(BaseCommand):
    help = "Seeds comprehensive reference data for Football, Cricket, and Tennis."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting sports reference data seed...")

        # ─── 1. Sports ────────────────────────────────────────────────────────
        sports_data = [
            {"slug": "football", "name": "Football", "icon_url": "https://cdn.example.com/icons/football.svg"},
            {"slug": "cricket", "name": "Cricket", "icon_url": "https://cdn.example.com/icons/cricket.svg"},
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

        # ─── 2. Countries ─────────────────────────────────────────────────────
        countries_data = [
            {"iso_code": "GBR", "name": "United Kingdom"},
            {"iso_code": "ESP", "name": "Spain"},
            {"iso_code": "IND", "name": "India"},
            {"iso_code": "AUS", "name": "Australia"},
            {"iso_code": "USA", "name": "United States"},
            {"iso_code": "GER", "name": "Germany"},
            {"iso_code": "FRA", "name": "France"},
            {"iso_code": "ITA", "name": "Italy"},
            {"iso_code": "BRA", "name": "Brazil"},
            {"iso_code": "ARG", "name": "Argentina"},
            {"iso_code": "PRT", "name": "Portugal"},
            {"iso_code": "ZAF", "name": "South Africa"},
            {"iso_code": "NZL", "name": "New Zealand"},
            {"iso_code": "PAK", "name": "Pakistan"},
            {"iso_code": "POL", "name": "Poland"},
            {"iso_code": "SRB", "name": "Serbia"},
            {"iso_code": "KAZ", "name": "Kazakhstan"},
        ]
        countries = {}
        for item in countries_data:
            c, created = Country.objects.update_or_create(
                iso_code=item["iso_code"],
                defaults={"name": item["name"]},
            )
            countries[item["iso_code"]] = c

        # ─── 3. Competitions ──────────────────────────────────────────────────
        competitions_data = [
            # Football Competitions
            {
                "key": "football_epl",
                "sport": sports["football"],
                "country": countries["GBR"],
                "name": "Premier League",
                "short_name": "EPL",
                "season": "2025-26",
                "competition_type": "league",
            },
            {
                "key": "football_laliga",
                "sport": sports["football"],
                "country": countries["ESP"],
                "name": "La Liga",
                "short_name": "La Liga",
                "season": "2025-26",
                "competition_type": "league",
            },
            {
                "key": "football_ucl",
                "sport": sports["football"],
                "country": None,
                "name": "UEFA Champions League",
                "short_name": "UCL",
                "season": "2025-26",
                "competition_type": "cup",
            },
            {
                "key": "football_worldcup",
                "sport": sports["football"],
                "country": None,
                "name": "FIFA World Cup",
                "short_name": "World Cup",
                "season": "2026",
                "competition_type": "international",
            },
            # Cricket Competitions
            {
                "key": "cricket_ipl",
                "sport": sports["cricket"],
                "country": countries["IND"],
                "name": "Indian Premier League",
                "short_name": "IPL",
                "season": "2026",
                "competition_type": "league",
            },
            {
                "key": "cricket_t20_wc",
                "sport": sports["cricket"],
                "country": None,
                "name": "ICC Men's T20 World Cup",
                "short_name": "T20 WC",
                "season": "2026",
                "competition_type": "international",
            },
            {
                "key": "cricket_bbl",
                "sport": sports["cricket"],
                "country": countries["AUS"],
                "name": "Big Bash League",
                "short_name": "BBL",
                "season": "2025-26",
                "competition_type": "league",
            },
            # Tennis Tournaments (Competitions)
            {
                "key": "tennis_wimbledon",
                "sport": sports["tennis"],
                "country": countries["GBR"],
                "name": "Wimbledon Championships",
                "short_name": "Wimbledon",
                "season": "2026",
                "competition_type": "league",
            },
            {
                "key": "tennis_roland_garros",
                "sport": sports["tennis"],
                "country": countries["FRA"],
                "name": "Roland Garros (French Open)",
                "short_name": "Roland Garros",
                "season": "2026",
                "competition_type": "league",
            },
            {
                "key": "tennis_us_open",
                "sport": sports["tennis"],
                "country": countries["USA"],
                "name": "US Open",
                "short_name": "US Open",
                "season": "2026",
                "competition_type": "league",
            },
            {
                "key": "tennis_australian_open",
                "sport": sports["tennis"],
                "country": countries["AUS"],
                "name": "Australian Open",
                "short_name": "Aus Open",
                "season": "2026",
                "competition_type": "league",
            },
            {
                "key": "tennis_atp_finals",
                "sport": sports["tennis"],
                "country": countries["ITA"],
                "name": "Nitto ATP Finals",
                "short_name": "ATP Finals",
                "season": "2026",
                "competition_type": "cup",
            },
            {
                "key": "tennis_indian_wells",
                "sport": sports["tennis"],
                "country": countries["USA"],
                "name": "BNP Paribas Open (Indian Wells)",
                "short_name": "Indian Wells",
                "season": "2026",
                "competition_type": "cup",
            },
        ]
        competitions = {}
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
            competitions[item["key"]] = c
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Competition: {c.name}")

        # ─── 4. Teams ─────────────────────────────────────────────────────────
        teams_data = [
            # Football Clubs (EPL)
            {"key": "fb_ars", "sport": sports["football"], "country": countries["GBR"], "name": "Arsenal", "short_name": "ARS", "team_type": "club"},
            {"key": "fb_mci", "sport": sports["football"], "country": countries["GBR"], "name": "Manchester City", "short_name": "MCI", "team_type": "club"},
            {"key": "fb_liv", "sport": sports["football"], "country": countries["GBR"], "name": "Liverpool", "short_name": "LIV", "team_type": "club"},
            {"key": "fb_che", "sport": sports["football"], "country": countries["GBR"], "name": "Chelsea FC", "short_name": "CHE", "team_type": "club"},
            {"key": "fb_mun", "sport": sports["football"], "country": countries["GBR"], "name": "Manchester United", "short_name": "MUN", "team_type": "club"},
            {"key": "fb_tot", "sport": sports["football"], "country": countries["GBR"], "name": "Tottenham Hotspur", "short_name": "TOT", "team_type": "club"},
            {"key": "fb_avl", "sport": sports["football"], "country": countries["GBR"], "name": "Aston Villa", "short_name": "AVL", "team_type": "club"},
            {"key": "fb_new", "sport": sports["football"], "country": countries["GBR"], "name": "Newcastle United", "short_name": "NEW", "team_type": "club"},

            # Football Clubs (La Liga & Continental)
            {"key": "fb_rma", "sport": sports["football"], "country": countries["ESP"], "name": "Real Madrid", "short_name": "RMA", "team_type": "club"},
            {"key": "fb_bar", "sport": sports["football"], "country": countries["ESP"], "name": "FC Barcelona", "short_name": "BAR", "team_type": "club"},
            {"key": "fb_atm", "sport": sports["football"], "country": countries["ESP"], "name": "Atletico Madrid", "short_name": "ATM", "team_type": "club"},
            {"key": "fb_bay", "sport": sports["football"], "country": countries["GER"], "name": "Bayern Munich", "short_name": "BAY", "team_type": "club"},
            {"key": "fb_psg", "sport": sports["football"], "country": countries["FRA"], "name": "Paris Saint-Germain", "short_name": "PSG", "team_type": "club"},

            # Football National Teams
            {"key": "fb_nat_eng", "sport": sports["football"], "country": countries["GBR"], "name": "England National Football Team", "short_name": "England", "team_type": "national"},
            {"key": "fb_nat_esp", "sport": sports["football"], "country": countries["ESP"], "name": "Spain National Football Team", "short_name": "Spain", "team_type": "national"},
            {"key": "fb_nat_fra", "sport": sports["football"], "country": countries["FRA"], "name": "France National Football Team", "short_name": "France", "team_type": "national"},
            {"key": "fb_nat_ger", "sport": sports["football"], "country": countries["GER"], "name": "Germany National Football Team", "short_name": "Germany", "team_type": "national"},
            {"key": "fb_nat_bra", "sport": sports["football"], "country": countries["BRA"], "name": "Brazil National Football Team", "short_name": "Brazil", "team_type": "national"},
            {"key": "fb_nat_arg", "sport": sports["football"], "country": countries["ARG"], "name": "Argentina National Football Team", "short_name": "Argentina", "team_type": "national"},
            {"key": "fb_nat_prt", "sport": sports["football"], "country": countries["PRT"], "name": "Portugal National Football Team", "short_name": "Portugal", "team_type": "national"},

            # Cricket Franchises (IPL)
            {"key": "cr_rcb", "sport": sports["cricket"], "country": countries["IND"], "name": "Royal Challengers Bengaluru", "short_name": "RCB", "team_type": "club"},
            {"key": "cr_csk", "sport": sports["cricket"], "country": countries["IND"], "name": "Chennai Super Kings", "short_name": "CSK", "team_type": "club"},
            {"key": "cr_mi",  "sport": sports["cricket"], "country": countries["IND"], "name": "Mumbai Indians", "short_name": "MI", "team_type": "club"},
            {"key": "cr_kkr", "sport": sports["cricket"], "country": countries["IND"], "name": "Kolkata Knight Riders", "short_name": "KKR", "team_type": "club"},
            {"key": "cr_rr",  "sport": sports["cricket"], "country": countries["IND"], "name": "Rajasthan Royals", "short_name": "RR", "team_type": "club"},
            {"key": "cr_srh", "sport": sports["cricket"], "country": countries["IND"], "name": "Sunrisers Hyderabad", "short_name": "SRH", "team_type": "club"},
            {"key": "cr_gt",  "sport": sports["cricket"], "country": countries["IND"], "name": "Gujarat Titans", "short_name": "GT", "team_type": "club"},
            {"key": "cr_dc",  "sport": sports["cricket"], "country": countries["IND"], "name": "Delhi Capitals", "short_name": "DC", "team_type": "club"},
            {"key": "cr_lsg", "sport": sports["cricket"], "country": countries["IND"], "name": "Lucknow Super Giants", "short_name": "LSG", "team_type": "club"},
            {"key": "cr_pbks","sport": sports["cricket"], "country": countries["IND"], "name": "Punjab Kings", "short_name": "PBKS", "team_type": "club"},

            # Cricket National Teams
            {"key": "cr_nat_ind", "sport": sports["cricket"], "country": countries["IND"], "name": "India National Cricket Team", "short_name": "India", "team_type": "national"},
            {"key": "cr_nat_aus", "sport": sports["cricket"], "country": countries["AUS"], "name": "Australia National Cricket Team", "short_name": "Australia", "team_type": "national"},
            {"key": "cr_nat_eng", "sport": sports["cricket"], "country": countries["GBR"], "name": "England National Cricket Team", "short_name": "England", "team_type": "national"},
            {"key": "cr_nat_zaf", "sport": sports["cricket"], "country": countries["ZAF"], "name": "South Africa National Cricket Team", "short_name": "South Africa", "team_type": "national"},
            {"key": "cr_nat_nzl", "sport": sports["cricket"], "country": countries["NZL"], "name": "New Zealand National Cricket Team", "short_name": "New Zealand", "team_type": "national"},
            {"key": "cr_nat_pak", "sport": sports["cricket"], "country": countries["PAK"], "name": "Pakistan National Cricket Team", "short_name": "Pakistan", "team_type": "national"},
        ]
        teams = {}
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
            teams[item["key"]] = t
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Team: {t.name}")

        # ─── 5. Competition-Team M2M Linkages ─────────────────────────────────
        rosters = [
            # Premier League Roster
            ("football_epl", ["fb_ars", "fb_mci", "fb_liv", "fb_che", "fb_mun", "fb_tot", "fb_avl", "fb_new"]),
            # La Liga Roster
            ("football_laliga", ["fb_rma", "fb_bar", "fb_atm"]),
            # Champions League Roster
            ("football_ucl", ["fb_rma", "fb_mci", "fb_bay", "fb_psg", "fb_ars", "fb_bar", "fb_liv", "fb_atm"]),
            # FIFA World Cup Roster
            ("football_worldcup", ["fb_nat_eng", "fb_nat_esp", "fb_nat_fra", "fb_nat_ger", "fb_nat_bra", "fb_nat_arg", "fb_nat_prt"]),
            # IPL Roster
            ("cricket_ipl", ["cr_rcb", "cr_csk", "cr_mi", "cr_kkr", "cr_rr", "cr_srh", "cr_gt", "cr_dc", "cr_lsg", "cr_pbks"]),
            # T20 World Cup Roster
            ("cricket_t20_wc", ["cr_nat_ind", "cr_nat_aus", "cr_nat_eng", "cr_nat_zaf", "cr_nat_nzl", "cr_nat_pak"]),
        ]

        comp_team_count = 0
        for comp_key, team_keys in rosters:
            comp_obj = competitions[comp_key]
            for t_key in team_keys:
                team_obj = teams[t_key]
                _, created = CompetitionTeam.objects.update_or_create(
                    competition=comp_obj,
                    team=team_obj,
                    season=comp_obj.season,
                    defaults={"is_active": True},
                )
                if created:
                    comp_team_count += 1

        self.stdout.write(f"  Linked {comp_team_count} Competition-Team relationships.")

        # ─── 6. Players (Focus on Tennis Stars & Cricket/Football Talents) ─────
        players_data = [
            # Tennis Champions (ATP Men's Singles)
            {"sport": sports["tennis"], "nationality": countries["ESP"], "name": "Carlos Alcaraz", "position": "ATP #1 · Singles"},
            {"sport": sports["tennis"], "nationality": countries["ITA"], "name": "Jannik Sinner", "position": "ATP #2 · Singles"},
            {"sport": sports["tennis"], "nationality": countries["SRB"], "name": "Novak Djokovic", "position": "ATP #3 · Singles"},
            {"sport": sports["tennis"], "nationality": countries["GER"], "name": "Alexander Zverev", "position": "ATP #4 · Singles"},
            {"sport": sports["tennis"], "nationality": countries["USA"], "name": "Taylor Fritz", "position": "ATP #5 · Singles"},

            # Tennis Champions (WTA Women's Singles)
            {"sport": sports["tennis"], "nationality": countries["POL"], "name": "Iga Swiatek", "position": "WTA #1 · Singles"},
            {"sport": sports["tennis"], "nationality": countries["USA"], "name": "Coco Gauff", "position": "WTA #2 · Singles"},
            {"sport": sports["tennis"], "nationality": countries["KAZ"], "name": "Elena Rybakina", "position": "WTA #3 · Singles"},
            {"sport": sports["tennis"], "nationality": countries["USA"], "name": "Jessica Pegula", "position": "WTA #4 · Singles"},

            # Cricket Stars
            {"sport": sports["cricket"], "nationality": countries["IND"], "name": "Virat Kohli", "position": "Top-Order Batsman"},
            {"sport": sports["cricket"], "nationality": countries["IND"], "name": "Rohit Sharma", "position": "Opening Batsman"},
            {"sport": sports["cricket"], "nationality": countries["IND"], "name": "Jasprit Bumrah", "position": "Fast Bowler"},
            {"sport": sports["cricket"], "nationality": countries["AUS"], "name": "Pat Cummins", "position": "Fast Bowler / All-Rounder"},

            # Football Stars
            {"sport": sports["football"], "nationality": countries["ESP"], "name": "Lamine Yamal", "position": "Winger"},
            {"sport": sports["football"], "nationality": countries["GBR"], "name": "Jude Bellingham", "position": "Midfielder"},
            {"sport": sports["football"], "nationality": countries["FRA"], "name": "Kylian Mbappé", "position": "Forward"},
            {"sport": sports["football"], "nationality": countries["ARG"], "name": "Lionel Messi", "position": "Forward"},
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
