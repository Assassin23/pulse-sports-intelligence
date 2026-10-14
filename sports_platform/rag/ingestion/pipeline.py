"""
Document Ingestion Pipeline — Milestone 9.

Processes raw documents: computes SHA-256 for idempotent deduplication,
splits content using SemanticChunker, generates dense vector embeddings,
and stores document and chunks with rich metadata.
"""
from dataclasses import dataclass
from typing import List, Optional, Any
from datetime import datetime, timezone
import hashlib
import logging
import uuid
from django.db import transaction
from django.utils.dateparse import parse_datetime

from sports_platform.rag.models import RAGDocument, RAGChunk
from sports_platform.rag.chunking.semantic_chunker import SemanticChunker
from sports_platform.rag.embeddings import get_embedder, BaseEmbedder
from sports_platform.sports.models import Sport

logger = logging.getLogger(__name__)


@dataclass
class RawDocument:
    title: str
    content: str
    source_url: Optional[str] = ""
    document_type: str = "article"  # 'team_profile', 'player_profile', 'competition_rules', 'article', 'terminology', 'h2h_history'
    sport: Optional[Any] = None  # Sport instance, slug ('cricket', 'football', 'tennis'), or UUID
    entity_type: Optional[str] = ""  # 'team', 'player', 'competition', 'rule'
    entity_id: Optional[Any] = None
    published_at: Optional[Any] = None
    language: str = "en"


class DocumentIngestionPipeline:
    """
    Orchestrates end-to-end ingestion of sports knowledge documents into pgvector.
    - Idempotent: Skips or returns existing document if content hash matches.
    - Transactional: Ensures document and its chunk vectors are created atomically.
    """

    def __init__(
        self,
        chunker: Optional[SemanticChunker] = None,
        embedder: Optional[BaseEmbedder] = None,
    ):
        self._chunker = chunker or SemanticChunker()
        self._embedder = embedder or get_embedder()

    def _resolve_sport(self, sport_val: Optional[Any]) -> Optional[Sport]:
        """Resolve sport from slug, name, UUID, or Sport instance."""
        if not sport_val:
            return None
        if isinstance(sport_val, Sport):
            return sport_val
        val_str = str(sport_val).strip()
        try:
            # Check if valid UUID
            val_uuid = uuid.UUID(val_str)
            return Sport.objects.filter(id=val_uuid).first()
        except (ValueError, AttributeError):
            pass
        return Sport.objects.filter(slug__iexact=val_str).first() or Sport.objects.filter(name__iexact=val_str).first()

    def _parse_published_at(self, val: Optional[Any]) -> Optional[datetime]:
        if not val:
            return None
        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=timezone.utc)
            return val
        if isinstance(val, str):
            dt = parse_datetime(val)
            if dt and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        return None

    def ingest(self, document: RawDocument, force_reindex: bool = False) -> str:
        """
        Ingests a document into the knowledge base.
        Returns the document UUID string.
        """
        clean_content = document.content.strip()
        if not clean_content:
            raise ValueError("Document content cannot be empty.")

        # 1. Compute content hash for deduplication
        content_hash = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()

        # 2. Check if already ingested (idempotency check)
        existing = RAGDocument.objects.filter(content_hash=content_hash).first()
        if existing and not force_reindex:
            if existing.is_active and existing.chunks.exists():
                logger.info(f"Document already ingested with hash {content_hash} (id={existing.id}). Skipping.")
                return str(existing.id)

        # 3. Resolve sport and entities
        sport_obj = self._resolve_sport(document.sport)
        published_dt = self._parse_published_at(document.published_at)

        entity_uuid = None
        if document.entity_id:
            try:
                entity_uuid = uuid.UUID(str(document.entity_id))
            except (ValueError, AttributeError):
                entity_uuid = None

        with transaction.atomic():
            # If force_reindex on existing hash, update existing document
            if existing:
                doc = existing
                doc.title = document.title
                doc.source_url = document.source_url or ""
                doc.document_type = document.document_type
                doc.sport = sport_obj
                doc.entity_type = document.entity_type or ""
                doc.entity_id = entity_uuid
                doc.raw_content = clean_content
                doc.published_at = published_dt
                doc.is_active = True
                doc.save()
                # Clear old chunks
                doc.chunks.all().delete()
            else:
                doc = RAGDocument.objects.create(
                    title=document.title,
                    source_url=document.source_url or "",
                    document_type=document.document_type,
                    sport=sport_obj,
                    entity_type=document.entity_type or "",
                    entity_id=entity_uuid,
                    content_hash=content_hash,
                    raw_content=clean_content,
                    language=document.language or "en",
                    published_at=published_dt,
                    is_active=True,
                )

            # 4. Chunk the document
            chunks = self._chunker.chunk(document)
            if not chunks:
                logger.warning(f"No chunks generated for document '{document.title}'.")
                return str(doc.id)

            # 5. Generate embeddings in batch
            chunk_texts = [c.text for c in chunks]
            embeddings = self._embedder.embed_batch(chunk_texts)

            # 6. Prepare chunks for bulk insert
            sport_slug = sport_obj.slug if sport_obj else (str(document.sport) if document.sport else "")
            chunk_objs = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                metadata = {
                    "document_type": document.document_type,
                    "sport": sport_slug,
                    "entity_type": document.entity_type or "",
                    "entity_id": str(entity_uuid) if entity_uuid else "",
                    "title": document.title,
                    "published_at": published_dt.isoformat() if published_dt else "",
                    "source_url": document.source_url or "",
                }
                chunk_objs.append(
                    RAGChunk(
                        document=doc,
                        chunk_index=i,
                        content=chunk.text,
                        token_count=chunk.token_count,
                        embedding=embedding,
                        metadata=metadata,
                    )
                )

            RAGChunk.objects.bulk_create(chunk_objs)

        logger.info(
            f"Successfully ingested RAG document '{doc.title}' (id={doc.id}) with {len(chunk_objs)} chunks."
        )
        return str(doc.id)
