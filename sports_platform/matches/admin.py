from django.contrib import admin
from sports_platform.matches.models import Match, MatchScore, MatchEvent, MatchOddsCurrent, MatchOddsHistory


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["id", "home_team", "away_team", "competition", "status", "scheduled_at"]
    list_filter = ["status", "sport", "competition"]
    search_fields = ["home_team__name", "away_team__name", "venue"]


@admin.register(MatchOddsCurrent)
class MatchOddsCurrentAdmin(admin.ModelAdmin):
    list_display = ["match", "provider_name", "market_type", "bookmaker", "is_open", "updated_at"]
    list_filter = ["provider_name", "market_type", "is_open"]
    search_fields = ["bookmaker", "match__home_team__name", "match__away_team__name"]


@admin.register(MatchOddsHistory)
class MatchOddsHistoryAdmin(admin.ModelAdmin):
    list_display = ["match", "provider_name", "market_type", "bookmaker", "recorded_at"]
    list_filter = ["provider_name", "market_type"]
    ordering = ["-recorded_at"]
