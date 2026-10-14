from django.contrib import admin
from sports_platform.rag.models import RAGDocument, RAGChunk


@admin.register(RAGDocument)
class RAGDocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "document_type", "sport", "entity_type", "is_active", "ingested_at"]
    list_filter = ["document_type", "sport", "is_active"]
    search_fields = ["title", "content_hash", "source_url"]


@admin.register(RAGChunk)
class RAGChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "chunk_index", "token_count", "created_at"]
    list_filter = ["document__document_type", "document__sport"]
    search_fields = ["content", "document__title"]
