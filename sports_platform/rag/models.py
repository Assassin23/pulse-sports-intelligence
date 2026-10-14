"""
RAG Models — Milestone 9.

Implements the document registry and chunk vector store defined in:
- docs/data-model/04-database-design.md
- docs/ai/09-ai-rag-architecture.md
"""
import uuid
from django.db import models

from django.contrib.postgres.indexes import GinIndex

try:
    from pgvector.django import VectorField, HnswIndex
except (ImportError, ModuleNotFoundError):
    # Graceful fallback for non-pgvector environments
    from django.db.models import JSONField as VectorField
    HnswIndex = None


class RAGDocument(models.Model):
    """
    Registry of knowledge documents ingested into the RAG system.
    Supports team profiles, player profiles, rules, articles, and terminology.
    Deduplicated via SHA-256 content_hash.
    """

    DOCUMENT_TYPES = [
        ("team_profile", "Team Profile"),
        ("player_profile", "Player Profile"),
        ("competition_rules", "Competition Rules"),
        ("article", "Article"),
        ("terminology", "Terminology"),
        ("h2h_history", "H2H History"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    source_url = models.CharField(max_length=1000, blank=True)
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    sport = models.ForeignKey(
        "sports.Sport",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rag_documents",
    )
    entity_type = models.CharField(max_length=20, blank=True)
    entity_id = models.UUIDField(null=True, blank=True, db_index=True)
    content_hash = models.CharField(max_length=64, unique=True, db_index=True)
    raw_content = models.TextField()
    language = models.CharField(max_length=10, default="en")
    published_at = models.DateTimeField(null=True, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "rag_documents"
        ordering = ["-ingested_at"]
        indexes = [
            models.Index(fields=["document_type", "sport"], name="idx_rag_docs_type_sport"),
            models.Index(fields=["entity_type", "entity_id"], name="idx_rag_docs_entity"),
        ]

    def __str__(self) -> str:
        return f"[{self.document_type}] {self.title}"

    @property
    def chunk_count(self) -> int:
        if hasattr(self, "_chunk_count"):
            return self._chunk_count
        return self.chunks.count()

    @chunk_count.setter
    def chunk_count(self, value: int):
        self._chunk_count = value


def get_vector_field():
    """Return VectorField with 1536 dimensions if pgvector is available."""
    if hasattr(VectorField, "__call__") and VectorField is not models.JSONField:
        try:
            return VectorField(dimensions=1536, null=True, blank=True)
        except TypeError:
            return VectorField(null=True, blank=True)
    return models.JSONField(default=list, null=True, blank=True)


def _get_chunk_indexes():
    indexes = [
        models.Index(fields=["document", "chunk_index"], name="idx_rag_chunks_doc_idx"),
        GinIndex(fields=["metadata"], name="idx_rag_chunks_metadata"),
    ]
    if HnswIndex is not None:
        indexes.append(
            HnswIndex(
                name="idx_rag_chunks_embedding",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        )
    return indexes


class RAGChunk(models.Model):
    """
    Semantic chunk derived from a RAGDocument, stored with 1536-dimensional embedding.
    Indexed using HNSW (vector_cosine_ops) for fast approximate nearest neighbor retrieval.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        RAGDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.IntegerField()
    content = models.TextField()
    token_count = models.IntegerField(null=True, blank=True)
    embedding = get_vector_field()
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rag_chunks"
        unique_together = [("document", "chunk_index")]
        ordering = ["document", "chunk_index"]
        indexes = _get_chunk_indexes()

    def __str__(self) -> str:
        return f"Chunk #{self.chunk_index} of {self.document.title}"
