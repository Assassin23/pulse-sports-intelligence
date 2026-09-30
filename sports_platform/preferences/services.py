"""
Preferences service layer.
Enforces the max-3-sports rule, entity validation, and builds aggregated preference representations.
"""
from typing import Any, Dict, List, Optional
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from sports_platform.preferences.models import (
    UserFollowedEntity,
    UserNotificationPreference,
    UserSportPreference,
)
from sports_platform.sports.models import Competition, Country, Player, Sport, Team

User = get_user_model()
MAX_SPORTS = 3


class PreferenceService:
    @staticmethod
    def get_user_preferences(user: Any) -> Dict[str, Any]:
        """
        Builds the structured preferences response for a user:
        {
            "sports": [
                {
                    "sport": {"id": "...", "slug": "cricket", "name": "Cricket"},
                    "following": {
                        "teams": [...],
                        "competitions": [...],
                        "countries": [...],
                        "players": [...]
                    }
                }
            ],
            "max_sports": 3,
            "sports_remaining": 1
        }
        """
        user_sports = (
            UserSportPreference.objects.filter(user=user)
            .select_related("sport")
            .order_by("created_at")
        )
        followed_entities = list(
            UserFollowedEntity.objects.filter(user=user).select_related("sport")
        )

        # Pre-fetch followed details to avoid N+1 queries
        team_ids = [e.entity_id for e in followed_entities if e.entity_type == "team"]
        comp_ids = [e.entity_id for e in followed_entities if e.entity_type == "competition"]
        country_ids = [e.entity_id for e in followed_entities if e.entity_type == "country"]
        player_ids = [e.entity_id for e in followed_entities if e.entity_type == "player"]

        teams_map = {t.id: t for t in Team.objects.filter(id__in=team_ids)}
        comps_map = {c.id: c for c in Competition.objects.filter(id__in=comp_ids)}
        countries_map = {c.id: c for c in Country.objects.filter(id__in=country_ids)}
        players_map = {p.id: p for p in Player.objects.filter(id__in=player_ids)}

        sports_data = []
        for pref in user_sports:
            sport = pref.sport
            sport_follows = [e for e in followed_entities if e.sport_id == sport.id]

            teams = []
            for e in sport_follows:
                if e.entity_type == "team" and e.entity_id in teams_map:
                    t = teams_map[e.entity_id]
                    teams.append({
                        "id": str(t.id),
                        "name": t.name,
                        "short_name": t.short_name,
                        "logo_url": t.logo_url,
                    })

            competitions = []
            for e in sport_follows:
                if e.entity_type == "competition" and e.entity_id in comps_map:
                    c = comps_map[e.entity_id]
                    competitions.append({
                        "id": str(c.id),
                        "name": c.name,
                        "short_name": c.short_name,
                        "season": c.season,
                        "logo_url": c.logo_url,
                    })

            countries = []
            for e in sport_follows:
                if e.entity_type == "country" and e.entity_id in countries_map:
                    c = countries_map[e.entity_id]
                    countries.append({
                        "id": str(c.id),
                        "name": c.name,
                        "iso_code": c.iso_code,
                    })

            players = []
            for e in sport_follows:
                if e.entity_type == "player" and e.entity_id in players_map:
                    p = players_map[e.entity_id]
                    players.append({
                        "id": str(p.id),
                        "name": p.name,
                        "position": p.position,
                        "photo_url": p.photo_url,
                    })

            sports_data.append({
                "sport": {
                    "id": str(sport.id),
                    "slug": sport.slug,
                    "name": sport.name,
                    "icon_url": sport.icon_url,
                },
                "following": {
                    "teams": teams,
                    "competitions": competitions,
                    "countries": countries,
                    "players": players,
                },
            })

        count = len(sports_data)
        return {
            "sports": sports_data,
            "max_sports": MAX_SPORTS,
            "sports_remaining": max(0, MAX_SPORTS - count),
        }

    @classmethod
    def validate_entity(cls, sport: Sport, entity_type: str, entity_id: uuid.UUID) -> Any:
        """Verify the entity exists and belongs to the given sport."""
        if entity_type == "team":
            try:
                return Team.objects.get(id=entity_id, sport=sport, is_active=True)
            except Team.DoesNotExist:
                raise ValidationError({"entity_id": f"Team {entity_id} not found in sport {sport.slug}."})
        elif entity_type == "competition":
            try:
                return Competition.objects.get(id=entity_id, sport=sport, is_active=True)
            except Competition.DoesNotExist:
                raise ValidationError({"entity_id": f"Competition {entity_id} not found in sport {sport.slug}."})
        elif entity_type == "country":
            try:
                return Country.objects.get(id=entity_id)
            except Country.DoesNotExist:
                raise ValidationError({"entity_id": f"Country {entity_id} not found."})
        elif entity_type == "player":
            try:
                return Player.objects.get(id=entity_id, sport=sport, is_active=True)
            except Player.DoesNotExist:
                raise ValidationError({"entity_id": f"Player {entity_id} not found in sport {sport.slug}."})
        else:
            raise ValidationError({"entity_type": f"Invalid entity_type: {entity_type}."})

    @classmethod
    def follow_entity(
        cls, user: Any, sport_slug: str, entity_type: str, entity_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Follow an entity, adding the sport if not already followed (if under limit)."""
        try:
            sport = Sport.objects.get(slug=sport_slug, is_active=True)
        except Sport.DoesNotExist:
            raise ValidationError({"sport": f"Sport '{sport_slug}' does not exist or is inactive."})

        entity_obj = cls.validate_entity(sport, entity_type, entity_id)

        with transaction.atomic():
            # Check if sport is already in user preferences
            sport_pref = UserSportPreference.objects.filter(user=user, sport=sport).first()
            if not sport_pref:
                current_sports_count = UserSportPreference.objects.filter(user=user).count()
                if current_sports_count >= MAX_SPORTS:
                    raise ValidationError(
                        {"error": "MAX_SPORTS_REACHED", "message": f"Maximum {MAX_SPORTS} sports allowed."}
                    )
                UserSportPreference.objects.create(user=user, sport=sport)

            # Follow entity
            follow_obj, created = UserFollowedEntity.objects.get_or_create(
                user=user,
                sport=sport,
                entity_type=entity_type,
                entity_id=entity_id,
            )

        entity_name = getattr(entity_obj, "name", str(entity_id))
        return {"message": f"Now following {entity_name} in {sport.name}."}

    @classmethod
    def unfollow_entity(
        cls, user: Any, entity_type: str, entity_id: uuid.UUID
    ) -> None:
        """Unfollow an entity."""
        deleted_count, _ = UserFollowedEntity.objects.filter(
            user=user,
            entity_type=entity_type,
            entity_id=entity_id,
        ).delete()
        if deleted_count == 0:
            raise NotFound(detail=f"Follow relation for {entity_type} {entity_id} not found.")

    @classmethod
    def bulk_update_preferences(
        cls, user: Any, sports_slugs: List[str], following_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Full replacement of user preferences."""
        if len(sports_slugs) > MAX_SPORTS:
            raise ValidationError(
                {"error": "MAX_SPORTS_REACHED", "message": f"Maximum {MAX_SPORTS} sports allowed."}
            )

        sports = list(Sport.objects.filter(slug__in=sports_slugs, is_active=True))
        if len(sports) != len(set(sports_slugs)):
            found_slugs = {s.slug for s in sports}
            missing = set(sports_slugs) - found_slugs
            raise ValidationError({"sports": f"Unknown sports: {', '.join(missing)}"})

        sports_by_slug = {s.slug: s for s in sports}

        # Validate all follow entities
        validated_follows = []
        for item in following_data:
            s_slug = item.get("sport")
            if s_slug not in sports_by_slug:
                raise ValidationError({
                    "following": f"Cannot follow entity for sport '{s_slug}' which is not in selected sports."
                })
            sport_obj = sports_by_slug[s_slug]
            e_type = item.get("entity_type")
            e_id = item.get("entity_id")
            cls.validate_entity(sport_obj, e_type, e_id)
            validated_follows.append((sport_obj, e_type, e_id))

        with transaction.atomic():
            # Clear old
            UserFollowedEntity.objects.filter(user=user).delete()
            UserSportPreference.objects.filter(user=user).delete()

            # Create new sports
            for s in sports:
                UserSportPreference.objects.create(user=user, sport=s)

            # Create new follows
            for s_obj, e_type, e_id in validated_follows:
                UserFollowedEntity.objects.create(
                    user=user,
                    sport=s_obj,
                    entity_type=e_type,
                    entity_id=e_id,
                )

        return cls.get_user_preferences(user)
