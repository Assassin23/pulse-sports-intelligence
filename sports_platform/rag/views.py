"""
RAG Views — Milestone 9.

Implements:
1. POST /api/v1/admin/rag/ingest (Admin document ingestion)
2. ViewSet /api/v1/admin/rag/documents/ (Admin document registry)
3. POST /api/v1/rag/search/ (Retrieval testing & knowledge search)
"""
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count

from sports_platform.rag.models import RAGDocument
from sports_platform.rag.serializers import (
    RAGDocumentSerializer,
    RAGDocumentDetailSerializer,
    RAGIngestRequestSerializer,
    RAGSearchRequestSerializer,
    RAGSearchHitSerializer,
)
from sports_platform.rag.permissions import IsDataAdminOrStaff
from sports_platform.rag.ingestion.pipeline import DocumentIngestionPipeline, RawDocument
from sports_platform.rag.retrieval.retriever import HybridRetriever


class AdminRAGIngestView(APIView):
    """
    POST /api/v1/admin/rag/ingest
    Ingests a single raw document: deduplicates via SHA-256, chunks,
    generates 1536-dim embeddings, and persists chunks to pgvector.
    Permission: Data Admin or Staff.
    """

    permission_classes = [IsAuthenticated, IsDataAdminOrStaff]

    def post(self, request, *args, **kwargs):
        serializer = RAGIngestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        raw_doc = RawDocument(
            title=data["title"],
            content=data["content"],
            source_url=data.get("source_url", ""),
            document_type=data.get("document_type", "article"),
            sport=data.get("sport"),
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id"),
            published_at=data.get("published_at"),
            language=data.get("language", "en"),
        )

        pipeline = DocumentIngestionPipeline()
        doc_id = pipeline.ingest(raw_doc, force_reindex=data.get("force_reindex", False))

        doc = RAGDocument.objects.filter(id=doc_id).annotate(chunk_count=Count("chunks")).first()
        chunk_count = doc.chunk_count if doc else 0

        return Response(
            {
                "status": "success",
                "message": "Document successfully ingested into RAG store.",
                "document_id": doc_id,
                "title": doc.title if doc else data["title"],
                "chunks_created": chunk_count,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminRAGDocumentViewSet(viewsets.ModelViewSet):
    """
    Admin endpoints to list, inspect, and manage RAG documents.
    GET /api/v1/admin/rag/documents/
    GET /api/v1/admin/rag/documents/{id}/
    DELETE /api/v1/admin/rag/documents/{id}/
    """

    permission_classes = [IsAuthenticated, IsDataAdminOrStaff]
    queryset = RAGDocument.objects.annotate(chunk_count=Count("chunks")).select_related("sport").order_by("-ingested_at")

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update"]:
            return RAGDocumentDetailSerializer
        return RAGDocumentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        sport = self.request.query_params.get("sport")
        doc_type = self.request.query_params.get("document_type")
        is_active = self.request.query_params.get("is_active")

        if sport:
            qs = qs.filter(sport__slug__iexact=sport)
        if doc_type:
            qs = qs.filter(document_type=doc_type)
        if is_active is not None:
            active_bool = is_active.lower() in ["true", "1", "yes"]
            qs = qs.filter(is_active=active_bool)
        return qs

    def perform_destroy(self, instance):
        # Soft-delete by setting is_active=False
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class RAGSearchView(APIView):
    """
    POST /api/v1/rag/search/
    Query the sports RAG knowledge base.
    Returns ranked chunks with similarity scores and citations.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = RAGSearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        retriever = HybridRetriever()
        results = retriever.retrieve(
            query=data["query"],
            sport=data.get("sport") or None,
            entity_type=data.get("entity_type") or None,
            entity_id=str(data["entity_id"]) if data.get("entity_id") else None,
            document_type=data.get("document_type") or None,
            top_n=data.get("top_n", 5),
        )

        hits = []
        for r in results:
            hits.append(
                {
                    "chunk_id": r.chunk_id,
                    "content": r.content,
                    "similarity": round(r.similarity, 4),
                    "document_id": r.document_id,
                    "document_title": r.document_title,
                    "document_type": r.document_type,
                    "sport": r.sport,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "source_url": r.source_url,
                    "published_at": r.published_at,
                    "citation": r.to_citation_dict(),
                }
            )

        hit_serializer = RAGSearchHitSerializer(hits, many=True)
        return Response(
            {
                "query": data["query"],
                "sport": data.get("sport") or None,
                "count": len(hits),
                "results": hit_serializer.data,
            },
            status=status.HTTP_200_OK,
        )
