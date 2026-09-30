"""
ProviderEntityMapping service.

Resolves external provider IDs → internal UUIDs and vice versa.
Also handles upsert / dedup of new entities discovered from provider data.
"""
import logging
import uuid
from typing import Optional

from django.db import transaction

from sports_platform.sports.models import (
    Competition,
    Country,
    Player,
    ProviderEntityMapping,
    Sport,
    Team,
)

logger = logging.getLogger(__name__)


class EntityMappingService:
    """
    Centralized service for resolving and registering provider entity IDs.

    Usage:
        service = EntityMappingService()
        internal_id = service.resolve(
            provider_name="api_football",
            entity_type="team",
            provider_entity_id="33",
        )
    """

    # ── Resolution ────────────────────────────────────────────────────────────

    @staticmethod
    def resolve(
        provider_name: str,
        entity_type: str,
        provider_entity_id: str,
    ) -> Optional[uuid.UUID]:
        """
        Return the internal UUID for a given provider entity.
        Returns None if no mapping exists yet.
        """
        try:
            mapping = ProviderEntityMapping.objects.get(
                provider_name=provider_name,
                entity_type=entity_type,
                provider_entity_id=str(provider_entity_id),
            )
            return mapping.internal_entity_id
        except ProviderEntityMapping.DoesNotExist:
            return None

    @staticmethod
    def reverse_resolve(
        provider_name: str,
        entity_type: str,
        internal_entity_id: uuid.UUID,
    ) -> Optional[str]:
        """Return the provider's external ID for an internal entity."""
        try:
            mapping = ProviderEntityMapping.objects.get(
                provider_name=provider_name,
                entity_type=entity_type,
                internal_entity_id=internal_entity_id,
            )
            return mapping.provider_entity_id
        except ProviderEntityMapping.DoesNotExist:
            return None

    @staticmethod
    def register(
        provider_name: str,
        entity_type: str,
        provider_entity_id: str,
        internal_entity_id: uuid.UUID,
    ) -> ProviderEntityMapping:
        """Create or fetch a mapping. Idempotent — safe to call multiple times."""
        mapping, created = ProviderEntityMapping.objects.get_or_create(
            provider_name=provider_name,
            entity_type=entity_type,
            provider_entity_id=str(provider_entity_id),
            defaults={"internal_entity_id": internal_entity_id},
        )
        if created:
            logger.info(
                "Entity mapping registered",
                extra={
                    "provider": provider_name,
                    "type": entity_type,
                    "provider_id": provider_entity_id,
                    "internal_id": str(internal_entity_id),
                },
            )
        return mapping

    # ── Upsert helpers ────────────────────────────────────────────────────────

    @classmethod
    def upsert_team(
        cls,
        provider_name: str,
        provider_team_id: str,
        sport: Sport,
        team_name: str,
        short_name: str = "",
        country: Optional[Country] = None,
        logo_url: str = "",
        team_type: str = "club",
    ) -> Team:
        """
        Find or create a Team from provider data, and register its mapping.
        Dedup by provider mapping first; fall back to name+sport match.
        """
        internal_id = cls.resolve(provider_name, "team", provider_team_id)
        if internal_id:
            try:
                return Team.objects.get(id=internal_id)
            except Team.DoesNotExist:
                pass

        with transaction.atomic():
            team, created = Team.objects.get_or_create(
                sport=sport,
                name=team_name,
                defaults={
                    "short_name": short_name or team_name[:50],
                    "country": country,
                    "logo_url": logo_url,
                    "team_type": team_type,
                    "is_active": True,
                },
            )
            cls.register(provider_name, "team", provider_team_id, team.id)

        if created:
            logger.info("New team created", extra={"team": team_name, "sport": sport.slug})
        return team

    @classmethod
    def upsert_competition(
        cls,
        provider_name: str,
        provider_competition_id: str,
        sport: Sport,
        competition_name: str,
        season: str = "",
        country: Optional[Country] = None,
        logo_url: str = "",
        competition_type: str = "league",
    ) -> Competition:
        """Find or create a Competition and register its mapping."""
        internal_id = cls.resolve(provider_name, "competition", provider_competition_id)
        if internal_id:
            try:
                return Competition.objects.get(id=internal_id)
            except Competition.DoesNotExist:
                pass

        with transaction.atomic():
            comp, created = Competition.objects.get_or_create(
                sport=sport,
                name=competition_name,
                season=season,
                defaults={
                    "country": country,
                    "logo_url": logo_url,
                    "competition_type": competition_type,
                    "is_active": True,
                },
            )
            cls.register(provider_name, "competition", provider_competition_id, comp.id)

        if created:
            logger.info(
                "New competition created",
                extra={"competition": competition_name, "sport": sport.slug, "season": season},
            )
        return comp
