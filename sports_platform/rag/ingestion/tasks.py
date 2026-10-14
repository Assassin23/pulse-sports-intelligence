"""
Celery tasks for RAG document ingestion — Milestone 9.
"""
from typing import Dict, Any, List
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="rag.ingest_document_async",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=180,
    time_limit=210,
)
def ingest_document_async(self, doc_data: Dict[str, Any], force_reindex: bool = False) -> str:
    """
    Asynchronously chunk, embed, and store a raw document.
    """
    try:
        from sports_platform.rag.ingestion.pipeline import DocumentIngestionPipeline, RawDocument

        raw_doc = RawDocument(
            title=doc_data.get("title", "Untitled"),
            content=doc_data.get("content", ""),
            source_url=doc_data.get("source_url", ""),
            document_type=doc_data.get("document_type", "article"),
            sport=doc_data.get("sport"),
            entity_type=doc_data.get("entity_type", ""),
            entity_id=doc_data.get("entity_id"),
            published_at=doc_data.get("published_at"),
            language=doc_data.get("language", "en"),
        )

        pipeline = DocumentIngestionPipeline()
        doc_id = pipeline.ingest(raw_doc, force_reindex=force_reindex)
        logger.info(f"Async RAG ingestion completed for document: {doc_id}")
        return doc_id
    except Exception as exc:
        logger.error(f"Error in async RAG document ingestion: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="rag.batch_ingest_async",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=600,
    time_limit=660,
)
def batch_ingest_async(self, docs_data: List[Dict[str, Any]], force_reindex: bool = False) -> List[str]:
    """
    Ingest a batch of documents sequentially in background worker.
    """
    from sports_platform.rag.ingestion.pipeline import DocumentIngestionPipeline, RawDocument

    pipeline = DocumentIngestionPipeline()
    results = []
    for doc_dict in docs_data:
        try:
            raw_doc = RawDocument(
                title=doc_dict.get("title", "Untitled"),
                content=doc_dict.get("content", ""),
                source_url=doc_dict.get("source_url", ""),
                document_type=doc_dict.get("document_type", "article"),
                sport=doc_dict.get("sport"),
                entity_type=doc_dict.get("entity_type", ""),
                entity_id=doc_dict.get("entity_id"),
                published_at=doc_dict.get("published_at"),
                language=doc_dict.get("language", "en"),
            )
            doc_id = pipeline.ingest(raw_doc, force_reindex=force_reindex)
            results.append(doc_id)
        except Exception as e:
            logger.error(f"Failed to ingest document '{doc_dict.get('title')}': {e}")
    return results
