"""
Serializers for personalized feed endpoint (Milestone 5).

Conforms to docs/api/11-api-design.md Section 11.4.
"""
from rest_framework import serializers

from sports_platform.sports.serializers import CompetitionListSerializer, TeamListSerializer


class FeedLastEventSerializer(serializers.Serializer):
    type = serializers.CharField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    minute = serializers.IntegerField(required=False, allow_null=True)
    player_name = serializers.CharField(required=False, allow_null=True)


class FeedMatchItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    sport = serializers.CharField()
    status = serializers.CharField()
    competition = CompetitionListSerializer()
    home_team = TeamListSerializer()
    away_team = TeamListSerializer()
    scheduled_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    venue = serializers.CharField(required=False, allow_blank=True)
    round = serializers.CharField(required=False, allow_blank=True)
    score = serializers.DictField(required=False, allow_null=True)
    last_event = FeedLastEventSerializer(required=False, allow_null=True)
    odds_summary = serializers.DictField(required=False, allow_null=True)
    relevance_tags = serializers.ListField(child=serializers.CharField(), default=list)
    data_freshness_seconds = serializers.IntegerField(required=False, allow_null=True)


class FeedPaginationSerializer(serializers.Serializer):
    next_cursor = serializers.CharField(allow_null=True)
    has_more = serializers.BooleanField()


class FeedResponseSerializer(serializers.Serializer):
    matches = FeedMatchItemSerializer(many=True)
    pagination = FeedPaginationSerializer()
