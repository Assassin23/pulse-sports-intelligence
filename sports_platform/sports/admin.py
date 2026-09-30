"""
Sports admin registration.
"""
from django.contrib import admin

from sports_platform.sports.models import (
    Competition,
    Country,
    Player,
    ProviderEntityMapping,
    Sport,
    Team,
)


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug"]


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ["name", "iso_code"]
    search_fields = ["name", "iso_code"]


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ["name", "sport", "country", "competition_type", "season", "is_active"]
    list_filter = ["sport", "competition_type", "is_active"]
    search_fields = ["name", "short_name"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "sport", "country", "team_type", "is_active"]
    list_filter = ["sport", "team_type", "is_active"]
    search_fields = ["name", "short_name"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "sport", "nationality", "position", "is_active"]
    list_filter = ["sport", "is_active"]
    search_fields = ["name"]


@admin.register(ProviderEntityMapping)
class ProviderEntityMappingAdmin(admin.ModelAdmin):
    list_display = ["provider_name", "entity_type", "provider_entity_id", "internal_entity_id"]
    list_filter = ["provider_name", "entity_type"]
    search_fields = ["provider_entity_id", "internal_entity_id"]
