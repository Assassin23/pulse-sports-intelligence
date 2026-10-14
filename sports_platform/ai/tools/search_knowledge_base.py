"""
Knowledge Base Search Tool — Milestone 10.

Executes dense vector search + metadata filtering across sports rules, team profiles,
player profiles, and terminology via pgvector RAG retriever.
"""
from typing import Dict, Any, Optional, List
import logging
from sports_platform.rag.retrieval.retriever import HybridRetriever

logger = logging.getLogger(__name__)


def search_knowledge_base(
    query: str,
    sport: Optional[str] = None,
    document_type: Optional[str] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """
    Query the sports knowledge base for context, background, and rules.
    """
    try:
        retriever = HybridRetriever()
        results = retriever.retrieve(
            query=query,
            sport=sport,
            document_type=document_type,
            top_n=top_n,
        )

        formatted_chunks: List[Dict[str, Any]] = []
        for r in results:
            formatted_chunks.append(
                {
                    "chunk_id": r.chunk_id,
                    "content": r.content,
                    "similarity": round(r.similarity, 4),
                    "title": r.document_title,
                    "document_type": r.document_type,
                    "sport": r.sport,
                    "citation": r.to_citation_dict(),
                }
            )

        return {
            "tool": "search_knowledge_base",
            "data": formatted_chunks,
            "error": None,
        }
    except Exception as exc:
        logger.error(f"Error querying knowledge base: {exc}", exc_info=True)
        return {
            "tool": "search_knowledge_base",
            "data": [],
            "error": str(exc),
        }
