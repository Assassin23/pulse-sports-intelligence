"""
Hybrid Retriever — Milestone 9.

Performs multi-stage contextual retrieval:
1. Dense vector similarity search (pgvector HNSW index with cosine distance)
2. Metadata filtering (by sport, entity_type, entity_id, document_type)
3. Freshness boost (+0.05 for documents published within 30 days)
4. Second-stage candidate re-ranking (top-k candidates -> top-n final)
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import math
import logging
from django.conf import settings
from django.db import connection

from sports_platform.rag.models import RAGChunk, RAGDocument
from sports_platform.rag.embeddings import get_embedder, BaseEmbedder
from sports_platform.rag.retrieval.reranker import get_reranker, BaseReranker

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    content: str
    similarity: float
    document_id: str
    document_title: str
    document_type: str
    sport: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_citation_dict(self) -> Dict[str, Any]:
        """Convert chunk into citation format for AI message sources."""
        return {
            "chunk_id": self.chunk_id,
            "title": self.document_title,
            "document_type": self.document_type,
            "sport": self.sport,
            "source_url": self.source_url or "",
            "published_at": self.published_at or "",
            "relevance": round(self.similarity, 4),
        }


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a, b in zip(vec_a, vec_b)))
    norm_b = math.sqrt(sum(b * b for a, b in zip(vec_a, vec_b)))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


class HybridRetriever:
    """
    RAG Hybrid Retriever combining vector ANN search, metadata filtering,
    publication freshness scoring, and candidate re-ranking.
    """

    def __init__(
        self,
        embedder: Optional[BaseEmbedder] = None,
        reranker: Optional[BaseReranker] = None,
        top_k_candidates: Optional[int] = None,
        top_n_final: Optional[int] = None,
        freshness_boost_days: Optional[int] = None,
        freshness_boost_score: Optional[float] = None,
    ):
        self._embedder = embedder or get_embedder()
        self._reranker = reranker or get_reranker()
        self.top_k_candidates = top_k_candidates or getattr(settings, "RAG_TOP_K_CANDIDATES", 20)
        self.top_n_final = top_n_final or getattr(settings, "RAG_TOP_N_FINAL", 5)
        self.freshness_boost_days = freshness_boost_days or getattr(settings, "RAG_FRESHNESS_BOOST_DAYS", 30)
        self.freshness_boost_score = freshness_boost_score or getattr(settings, "RAG_FRESHNESS_BOOST_SCORE", 0.05)

    def retrieve(
        self,
        query: str,
        sport: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        document_type: Optional[str] = None,
        top_n: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """
        Execute dense search + metadata filtering + freshness boost + re-ranking.
        """
        if not query or not query.strip():
            return []

        limit_final = top_n or self.top_n_final

        # 1. Embed query
        query_vector = self._embedder.embed_query(query.strip())

        # 2. Retrieve candidates
        candidates = self._vector_search_candidates(
            query_vector=query_vector,
            sport=sport,
            entity_type=entity_type,
            entity_id=entity_id,
            document_type=document_type,
            limit=self.top_k_candidates,
        )

        if not candidates:
            return []

        # 3. Apply freshness boost
        candidates = self._apply_freshness_boost(candidates)

        # 4. Re-rank top candidates
        if len(candidates) <= limit_final:
            return candidates[:limit_final]

        reranked = self._reranker.rerank(query=query, candidates=candidates, top_n=limit_final)
        return reranked[:limit_final]

    def _apply_freshness_boost(self, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self.freshness_boost_days)

        for chunk in chunks:
            if chunk.published_at:
                try:
                    pub_dt = datetime.fromisoformat(chunk.published_at.replace("Z", "+00:00"))
                    if pub_dt >= cutoff:
                        chunk.similarity = min(1.0, chunk.similarity + self.freshness_boost_score)
                except (ValueError, TypeError):
                    pass
        return chunks

    def _vector_search_candidates(
        self,
        query_vector: List[float],
        sport: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        document_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[RetrievedChunk]:
        """
        Executes vector search against PostgreSQL pgvector if available,
        otherwise falls back to in-memory cosine similarity across database chunks.
        """
        # Try native pgvector query on PostgreSQL
        if connection.vendor == "postgresql":
            try:
                return self._postgres_vector_search(
                    query_vector=query_vector,
                    sport=sport,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    document_type=document_type,
                    limit=limit,
                )
            except Exception as e:
                logger.warning(f"PostgreSQL pgvector search failed ({e}); falling back to ORM candidate search.")

        # Fallback for SQLite / non-pgvector test environments
        return self._python_vector_search(
            query_vector=query_vector,
            sport=sport,
            entity_type=entity_type,
            entity_id=entity_id,
            document_type=document_type,
            limit=limit,
        )

    def _postgres_vector_search(
        self,
        query_vector: List[float],
        sport: Optional[str],
        entity_type: Optional[str],
        entity_id: Optional[str],
        document_type: Optional[str],
        limit: int,
    ) -> List[RetrievedChunk]:
        vector_str = "[" + ",".join(str(x) for x in query_vector) + "]"

        where_clauses = ["d.is_active = TRUE"]
        where_params: List[Any] = []

        if sport:
            where_clauses.append("(c.metadata->>'sport' = %s OR s.slug = %s)")
            where_params.extend([sport.lower(), sport.lower()])
        if entity_type:
            where_clauses.append("c.metadata->>'entity_type' = %s")
            where_params.append(entity_type)
        if entity_id:
            where_clauses.append("c.metadata->>'entity_id' = %s")
            where_params.append(str(entity_id))
        if document_type:
            where_clauses.append("d.document_type = %s")
            where_params.append(document_type)

        where_sql = " AND ".join(where_clauses)
        params: List[Any] = [vector_str] + where_params + [vector_str, limit]

        sql = f"""
            SELECT
                c.id::text,
                c.content,
                1 - (c.embedding <=> %s::vector) AS similarity,
                d.id::text AS document_id,
                d.title AS document_title,
                d.document_type,
                COALESCE(s.slug, c.metadata->>'sport') AS sport_slug,
                c.metadata->>'entity_type' AS entity_type,
                c.metadata->>'entity_id' AS entity_id,
                d.source_url,
                d.published_at::text,
                c.metadata
            FROM rag_chunks c
            JOIN rag_documents d ON d.id = c.document_id
            LEFT JOIN sports s ON s.id = d.sport_id
            WHERE {where_sql}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s;
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                RetrievedChunk(
                    chunk_id=str(row[0]),
                    content=row[1],
                    similarity=float(row[2]) if row[2] is not None else 0.0,
                    document_id=str(row[3]),
                    document_title=row[4],
                    document_type=row[5],
                    sport=row[6],
                    entity_type=row[7],
                    entity_id=row[8],
                    source_url=row[9],
                    published_at=row[10],
                    metadata=row[11] if isinstance(row[11], dict) else {},
                )
            )
        return results

    def _python_vector_search(
        self,
        query_vector: List[float],
        sport: Optional[str],
        entity_type: Optional[str],
        entity_id: Optional[str],
        document_type: Optional[str],
        limit: int,
    ) -> List[RetrievedChunk]:
        """In-memory candidate scoring for test environments or non-pgvector backends."""
        qs = RAGChunk.objects.select_related("document", "document__sport").filter(document__is_active=True)

        if sport:
            sport_clean = sport.lower()
            qs = qs.filter(document__sport__slug__iexact=sport_clean) | qs.filter(metadata__sport=sport_clean)
        if entity_type:
            qs = qs.filter(metadata__entity_type=entity_type)
        if entity_id:
            qs = qs.filter(metadata__entity_id=str(entity_id))
        if document_type:
            qs = qs.filter(document__document_type=document_type)

        scored: List[RetrievedChunk] = []
        for chunk in qs:
            emb = chunk.embedding
            # If embedding is stored as vector string or list
            if isinstance(emb, str):
                try:
                    clean = emb.strip("[]")
                    emb = [float(x.strip()) for x in clean.split(",") if x.strip()]
                except Exception:
                    emb = []
            elif not isinstance(emb, list):
                emb = []

            sim = _cosine_similarity(query_vector, emb)
            doc = chunk.document
            sport_slug = doc.sport.slug if doc.sport else chunk.metadata.get("sport")
            pub_str = doc.published_at.isoformat() if doc.published_at else ""

            scored.append(
                RetrievedChunk(
                    chunk_id=str(chunk.id),
                    content=chunk.content,
                    similarity=round(sim, 4),
                    document_id=str(doc.id),
                    document_title=doc.title,
                    document_type=doc.document_type,
                    sport=sport_slug,
                    entity_type=chunk.metadata.get("entity_type") or doc.entity_type,
                    entity_id=chunk.metadata.get("entity_id") or (str(doc.entity_id) if doc.entity_id else None),
                    source_url=doc.source_url,
                    published_at=pub_str,
                    metadata=chunk.metadata,
                )
            )

        scored.sort(key=lambda c: c.similarity, reverse=True)
        return scored[:limit]
