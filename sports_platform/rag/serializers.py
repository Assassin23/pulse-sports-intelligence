"""
RAG Serializers — Milestone 9.
"""
from rest_framework import serializers
from sports_platform.rag.models import RAGDocument, RAGChunk


class RAGChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = RAGChunk
        fields = [
            "id",
            "chunk_index",
            "content",
            "token_count",
            "metadata",
            "created_at",
        ]


class RAGDocumentSerializer(serializers.ModelSerializer):
    chunk_count = serializers.IntegerField(read_only=True)
    sport_slug = serializers.CharField(source="sport.slug", read_only=True)

    class Meta:
        model = RAGDocument
        fields = [
            "id",
            "title",
            "source_url",
            "document_type",
            "sport",
            "sport_slug",
            "entity_type",
            "entity_id",
            "content_hash",
            "language",
            "published_at",
            "ingested_at",
            "is_active",
            "chunk_count",
        ]


class RAGDocumentDetailSerializer(RAGDocumentSerializer):
    chunks = RAGChunkSerializer(many=True, read_only=True)

    class Meta(RAGDocumentSerializer.Meta):
        fields = RAGDocumentSerializer.Meta.fields + ["raw_content", "chunks"]


class RAGIngestRequestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=500, required=True)
    content = serializers.CharField(required=True)
    source_url = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    document_type = serializers.ChoiceField(
        choices=RAGDocument.DOCUMENT_TYPES,
        default="article",
    )
    sport = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    entity_type = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    entity_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    published_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    language = serializers.CharField(max_length=10, default="en")
    force_reindex = serializers.BooleanField(default=False)


class RAGSearchRequestSerializer(serializers.Serializer):
    query = serializers.CharField(required=True, min_length=2)
    sport = serializers.CharField(required=False, allow_blank=True, default="")
    entity_type = serializers.CharField(required=False, allow_blank=True, default="")
    entity_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    document_type = serializers.CharField(required=False, allow_blank=True, default="")
    top_n = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)


class RAGSearchHitSerializer(serializers.Serializer):
    chunk_id = serializers.CharField()
    content = serializers.CharField()
    similarity = serializers.FloatField()
    document_id = serializers.CharField()
    document_title = serializers.CharField()
    document_type = serializers.CharField()
    sport = serializers.CharField(allow_null=True)
    entity_type = serializers.CharField(allow_null=True)
    entity_id = serializers.CharField(allow_null=True)
    source_url = serializers.CharField(allow_null=True)
    published_at = serializers.CharField(allow_null=True)
    citation = serializers.DictField()
