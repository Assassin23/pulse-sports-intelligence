"""
Matches API views — Milestone 3 & 4.

Endpoints:
  GET /api/v1/matches/upcoming/            — upcoming matches (Redis fast path → DB fallback)
  GET /api/v1/matches/live/               — currently live matches (Redis set)
  GET /api/v1/matches/{id}/               — single match with score + recent events
  GET /api/v1/matches/{id}/events/        — paginated event history (PostgreSQL)
"""
import logging
import time
from datetime import datetime, timezone

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sports_platform.matches.models import Match, MatchEvent
from sports_platform.matches.redis_store import get_match_store
from sports_platform.matches.serializers import (
    MatchDetailSerializer,
    MatchEventSerializer,
    MatchListSerializer,
)

logger = logging.getLogger(__name__)


class UpcomingMatchesView(APIView):
    """
    GET /api/v1/matches/upcoming/
    Query params:
      sport   — filter by sport slug (required)
      limit   — max results (default 20)
      hours   — look-ahead window in hours (default 48)

    Fast path: sorted set in Redis (matches:upcoming:{sport})
    Fallback:  PostgreSQL query (if Redis unavailable or empty)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        sport_slug = request.query_params.get("sport", "").strip()
        if not sport_slug:
            return Response(
                {"error": "sport query parameter is required"}, status=400
            )

        limit = min(int(request.query_params.get("limit", 20)), 50)
        hours = int(request.query_params.get("hours", 48))
        now = time.time()
        until = now + (hours * 3600)

        # ── Try Redis fast path ───────────────────────────────────────────────
        store = get_match_store()
        match_ids = []
        source = "cache"
        try:
            match_ids = store.get_upcoming_ids(sport_slug, from_ts=now, to_ts=until, limit=limit)
        except Exception as exc:
            logger.warning("Redis upcoming lookup failed", extra={"error": str(exc)})

        if not match_ids:
            # ── DB fallback ───────────────────────────────────────────────────
            source = "db"
            from sports_platform.sports.models import Sport
            qs = Match.objects.filter(
                sport__slug=sport_slug,
                status="scheduled",
                scheduled_at__gte=datetime.now(tz=timezone.utc),
            ).select_related("sport", "competition", "home_team", "away_team").order_by(
                "scheduled_at"
            )[:limit]
            data = MatchListSerializer(qs, many=True).data
            return Response({
                "sport": sport_slug,
                "source": source,
                "matches": data,
                "count": len(data),
            })

        # ── Fetch from DB by IDs (preserving Redis order) ─────────────────────
        matches_by_id = {
            str(m.id): m
            for m in Match.objects.filter(id__in=match_ids).select_related(
                "sport", "competition", "home_team", "away_team"
            )
        }
        ordered = [matches_by_id[mid] for mid in match_ids if mid in matches_by_id]
        data = MatchListSerializer(ordered, many=True).data

        return Response({
            "sport": sport_slug,
            "source": source,
            "matches": data,
            "count": len(data),
        })


class LiveMatchesView(APIView):
    """
    GET /api/v1/matches/live/
    Returns all currently live matches, served from Redis matches:live set.
    Includes current score from match:score:{id} for each match.

    Query params:
      sport — optional filter by sport slug
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        sport_filter = request.query_params.get("sport", "").strip()

        store = get_match_store()
        try:
            live_ids = store.get_live_match_ids()
        except Exception as exc:
            logger.warning("Redis live set failed, falling back to DB", extra={"error": str(exc)})
            live_ids = []

        if not live_ids:
            # DB fallback
            qs = Match.objects.filter(status="live")
            if sport_filter:
                qs = qs.filter(sport__slug=sport_filter)
            qs = qs.select_related("sport", "competition", "home_team", "away_team")
            return Response({
                "source": "db",
                "matches": MatchListSerializer(qs, many=True).data,
            })

        # Fetch matches
        qs = Match.objects.filter(id__in=live_ids)
        if sport_filter:
            qs = qs.filter(sport__slug=sport_filter)
        qs = qs.select_related("sport", "competition", "home_team", "away_team")

        result = []
        freshness_times = []
        for match in qs:
            match_data = MatchListSerializer(match).data
            # Attach live score from Redis
            score_cache = store.get_score(str(match.id))
            if score_cache:
                match_data["live_score"] = {
                    "score_data": score_cache.get("score_data"),
                    "status": score_cache.get("status"),
                    "sequence_number": score_cache.get("sequence_number"),
                }
                updated_at = int(score_cache.get("updated_at", 0))
                if updated_at:
                    age = int(time.time()) - updated_at
                    freshness_times.append(age)
                    match_data["data_freshness_seconds"] = age
            result.append(match_data)

        avg_freshness = int(sum(freshness_times) / len(freshness_times)) if freshness_times else None
        return Response({
            "source": "cache",
            "matches": result,
            "count": len(result),
            "avg_freshness_seconds": avg_freshness,
        })


class MatchDetailView(APIView):
    """
    GET /api/v1/matches/{id}/
    Returns match detail with:
      - Match metadata (from DB)
      - Live score (Redis fast path, DB fallback)
      - Recent events (Redis recent sorted set, up to 20)
      - data_freshness_seconds: age of score data in seconds
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, id: str) -> Response:
        match = get_object_or_404(
            Match.objects.select_related("sport", "competition", "home_team", "away_team"),
            id=id,
        )
        store = get_match_store()

        # ── Score (Redis → DB fallback) ───────────────────────────────────────
        score_data = None
        data_freshness_seconds = None
        score_source = "none"
        score_cache = store.get_score(str(match.id))
        if score_cache:
            score_data = score_cache.get("score_data")
            updated_at = int(score_cache.get("updated_at", 0))
            if updated_at:
                data_freshness_seconds = int(time.time()) - updated_at
            score_source = "cache"
        else:
            try:
                db_score = match.score
                score_data = db_score.score_data
                score_source = "db"
            except Match.score.RelatedObjectDoesNotExist:
                pass

        # ── Recent events (Redis) ─────────────────────────────────────────────
        recent_events = store.get_recent_events(str(match.id), limit=20)

        response_data = MatchDetailSerializer(match).data
        response_data.update({
            "score": score_data,
            "score_source": score_source,
            "recent_events": recent_events,
            "data_freshness_seconds": data_freshness_seconds,
        })
        return Response(response_data)


class MatchEventsView(APIView):
    """
    GET /api/v1/matches/{id}/events/
    Returns paginated match event history from PostgreSQL.
    Query params: page, page_size (default 50), event_type (filter)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, id: str) -> Response:
        match = get_object_or_404(Match, id=id)

        qs = MatchEvent.objects.filter(match=match).select_related(
            "player", "secondary_player", "team"
        )

        event_type = request.query_params.get("event_type", "").strip()
        if event_type:
            qs = qs.filter(event_type=event_type)

        # Manual pagination (simple, no extra deps)
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 50)), 100)
        offset = (page - 1) * page_size
        total = qs.count()
        events = qs[offset: offset + page_size]

        return Response({
            "match_id": str(match.id),
            "total": total,
            "page": page,
            "page_size": page_size,
            "events": MatchEventSerializer(events, many=True).data,
        })
