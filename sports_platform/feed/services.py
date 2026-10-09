"""
Personalized Feed Service Layer (Milestone 5).

Assembles a personalized match feed from followed entities, preferences,
live Redis state, and durable PostgreSQL records.
Handles 5-minute Redis caching, cache invalidation, and cursor pagination.
"""
import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from django.db.models import Q

from sports_platform.feed.redis_store import get_feed_store
from sports_platform.feed.serializers import FeedResponseSerializer
from sports_platform.matches.models import Match, MatchStatus
from sports_platform.matches.redis_store import get_match_store
from sports_platform.preferences.models import UserFollowedEntity, UserSportPreference

logger = logging.getLogger(__name__)


class FeedService:
    """
    Assembles, ranks, enriches, and caches personalized match feeds for users.
    """

    @classmethod
    def assemble_feed(
        cls,
        user: Any,
        status_filter: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Main entry point for GET /api/v1/feed.

        Returns:
            {
                "matches": [...],
                "pagination": {
                    "next_cursor": "...",
                    "has_more": True/False
                }
            }
        """
        page_size = max(1, min(page_size, 50))
        user_id_str = str(user.id)
        feed_store = get_feed_store()

        # ── 1. Fast-path: Check Redis cache (only for page 1) ─────────────────
        if not cursor:
            cached = feed_store.get_feed(user_id_str, status_filter=status_filter)
            if cached is not None:
                logger.debug("Feed cache HIT", extra={"user_id": user_id_str})
                return cached

        # ── 2. Decode cursor ──────────────────────────────────────────────────
        offset = cls._decode_cursor(cursor)

        # ── 3. Fetch user preferences & followed entities ─────────────────────
        sport_ids, sport_slugs, entity_map = cls._get_user_preferences(user)

        # ── 4. Query matches ──────────────────────────────────────────────────
        matches, total_count = cls._query_relevant_matches(
            sport_ids=sport_ids,
            entity_map=entity_map,
            status_filter=status_filter,
            offset=offset,
            limit=page_size + 1,  # Fetch one extra to detect has_more
        )

        has_more = len(matches) > page_size
        paged_matches = matches[:page_size]

        # ── 5. Enrich matches with live Redis state & relevance tags ──────────
        match_store = get_match_store()
        enriched_items = []
        all_relevant_match_ids = []

        for match in paged_matches:
            item = cls._enrich_match(match, entity_map, sport_slugs, match_store)
            enriched_items.append(item)
            all_relevant_match_ids.append(str(match.id))

        # ── 6. Build next cursor ──────────────────────────────────────────────
        next_cursor = None
        if has_more:
            next_cursor = cls._encode_cursor(offset + page_size)

        response_payload = {
            "matches": enriched_items,
            "pagination": {
                "next_cursor": next_cursor,
                "has_more": has_more,
            },
        }

        # ── 7. Cache in Redis (Page 1 only) ───────────────────────────────────
        if not cursor:
            feed_store.cache_feed(
                user_id=user_id_str,
                feed_data=response_payload,
                status_filter=status_filter,
            )
            # Also cache user's active followed match set in Redis
            feed_store.cache_user_matches(user_id_str, all_relevant_match_ids)

        return response_payload

    # ── Internal Helpers ──────────────────────────────────────────────────────

    @classmethod
    def _get_user_preferences(
        cls, user: Any
    ) -> Tuple[Set[uuid.UUID], Set[str], Dict[str, Set[uuid.UUID]]]:
        """
        Returns:
            (sport_ids, sport_slugs, {entity_type: set(entity_ids)})
        """
        sport_prefs = UserSportPreference.objects.filter(user=user).select_related("sport")
        sport_ids = {p.sport_id for p in sport_prefs}
        sport_slugs = {p.sport.slug for p in sport_prefs}

        followed_entities = UserFollowedEntity.objects.filter(user=user)
        entity_map: Dict[str, Set[uuid.UUID]] = {
            "team": set(),
            "competition": set(),
            "country": set(),
            "player": set(),
        }
        for fe in followed_entities:
            if fe.entity_type in entity_map:
                entity_map[fe.entity_type].add(fe.entity_id)

        return sport_ids, sport_slugs, entity_map

    @classmethod
    def _query_relevant_matches(
        cls,
        sport_ids: Set[uuid.UUID],
        entity_map: Dict[str, Set[uuid.UUID]],
        status_filter: Optional[str],
        offset: int,
        limit: int,
    ) -> Tuple[List[Match], int]:
        """
        Queries matches prioritizing live status, followed teams/competitions,
        and chronological schedule.
        """
        qs = Match.objects.select_related(
            "sport", "competition", "home_team", "away_team"
        )

        # Build status filter
        if status_filter:
            status_tokens = [s.strip().lower() for s in status_filter.split(",") if s.strip()]
            status_conditions = []
            for token in status_tokens:
                if token == "live":
                    status_conditions.extend([MatchStatus.LIVE, MatchStatus.HALF_TIME, MatchStatus.PAUSED])
                elif token == "upcoming":
                    status_conditions.append(MatchStatus.SCHEDULED)
                elif token == "completed":
                    status_conditions.append(MatchStatus.COMPLETED)
                else:
                    status_conditions.append(token)
            qs = qs.filter(status__in=status_conditions)

        # Preference filter: if user has preferences, prioritize them
        team_ids = entity_map.get("team", set())
        comp_ids = entity_map.get("competition", set())

        if sport_ids or team_ids or comp_ids:
            pref_q = Q()
            if sport_ids:
                pref_q |= Q(sport_id__in=sport_ids)
            if team_ids:
                pref_q |= Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids)
            if comp_ids:
                pref_q |= Q(competition_id__in=comp_ids)
            qs = qs.filter(pref_q)

        # Ranking logic:
        # 1. LIVE matches first
        # 2. Upcoming matches in chronological order
        # 3. Completed matches in reverse chronological order
        # We can implement a clean deterministic ordering:
        # CASE WHEN status IN ('live', 'half_time', 'paused') THEN 0
        #      WHEN status = 'scheduled' THEN 1
        #      ELSE 2 END, scheduled_at ASC
        from django.db.models import Case, Value, When, IntegerField

        ranked_qs = qs.annotate(
            status_priority=Case(
                When(status__in=[MatchStatus.LIVE, MatchStatus.HALF_TIME, MatchStatus.PAUSED], then=Value(0)),
                When(status=MatchStatus.SCHEDULED, then=Value(1)),
                When(status=MatchStatus.COMPLETED, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by("status_priority", "scheduled_at")

        total = ranked_qs.count()
        matches = list(ranked_qs[offset : offset + limit])
        return matches, total

    @classmethod
    def _enrich_match(
        cls,
        match: Match,
        entity_map: Dict[str, Set[uuid.UUID]],
        sport_slugs: Set[str],
        match_store: Any,
    ) -> Dict[str, Any]:
        """
        Enriches a Match instance with live score from Redis/DB,
        recent event history, relevance tags, and freshness metrics.
        """
        match_id_str = str(match.id)

        # ── 1. Score & freshness ──────────────────────────────────────────────
        score_data = None
        data_freshness_seconds = None

        # Check Redis score cache
        redis_score = match_store.get_score(match_id_str)
        if redis_score:
            score_data = redis_score.get("score_data")
            updated_at = int(redis_score.get("updated_at", 0))
            if updated_at:
                data_freshness_seconds = max(0, int(time.time()) - updated_at)
        else:
            # Fallback to DB
            try:
                db_score = match.score
                score_data = db_score.score_data
            except Exception:
                score_data = None

        # ── 2. Last event from Redis ──────────────────────────────────────────
        recent_events = match_store.get_recent_events(match_id_str, limit=1)
        last_event = None
        if recent_events:
            revt = recent_events[0]
            last_event = {
                "type": revt.get("event_type"),
                "description": revt.get("description"),
                "occurred_at": revt.get("occurred_at"),
                "minute": revt.get("minute"),
                "player_name": revt.get("player_name"),
            }

        # ── 3. Relevance tags ─────────────────────────────────────────────────
        relevance_tags = []
        team_ids = entity_map.get("team", set())
        comp_ids = entity_map.get("competition", set())

        if match.home_team_id in team_ids:
            relevance_tags.append(f"team:{match.home_team.short_name or match.home_team.name}")
        if match.away_team_id in team_ids:
            relevance_tags.append(f"team:{match.away_team.short_name or match.away_team.name}")
        if match.competition_id in comp_ids:
            relevance_tags.append(f"competition:{match.competition.short_name or match.competition.name}")
        if match.sport.slug in sport_slugs:
            relevance_tags.append(f"sport:{match.sport.slug}")

        return {
            "id": match.id,
            "sport": match.sport.slug,
            "status": match.status,
            "competition": {
                "id": match.competition.id,
                "name": match.competition.name,
                "short_name": match.competition.short_name,
                "season": match.competition.season,
                "competition_type": match.competition.competition_type,
                "logo_url": match.competition.logo_url,
            },
            "home_team": {
                "id": match.home_team.id,
                "name": match.home_team.name,
                "short_name": match.home_team.short_name,
                "logo_url": match.home_team.logo_url,
                "team_type": match.home_team.team_type,
            },
            "away_team": {
                "id": match.away_team.id,
                "name": match.away_team.name,
                "short_name": match.away_team.short_name,
                "logo_url": match.away_team.logo_url,
                "team_type": match.away_team.team_type,
            },
            "scheduled_at": match.scheduled_at,
            "started_at": match.started_at,
            "completed_at": match.completed_at,
            "venue": match.venue,
            "round": match.round,
            "score": score_data,
            "last_event": last_event,
            "odds_summary": None,  # Milestone 7 deliverable
            "relevance_tags": relevance_tags,
            "data_freshness_seconds": data_freshness_seconds,
        }

    # ── Cache Invalidation ───────────────────────────────────────────────────

    @classmethod
    def invalidate_feed_cache(cls, user_id: str) -> None:
        """Busts the feed cache for a user when their preferences change."""
        get_feed_store().invalidate_feed(user_id)
        logger.info("Feed cache invalidated for user", extra={"user_id": user_id})

    # ── Cursor encoding / decoding ───────────────────────────────────────────

    @staticmethod
    def _encode_cursor(offset: int) -> str:
        payload = json.dumps({"offset": offset})
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _decode_cursor(cursor_str: Optional[str]) -> int:
        if not cursor_str:
            return 0
        try:
            payload = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
            data = json.loads(payload)
            return max(0, int(data.get("offset", 0)))
        except Exception:
            return 0
