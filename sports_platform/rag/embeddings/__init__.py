"""
Embeddings package — Milestone 9.
"""
import logging
from typing import Optional
from django.conf import settings
from sports_platform.rag.embeddings.base import BaseEmbedder
from sports_platform.rag.embeddings.openai_embedder import OpenAIEmbedder
from sports_platform.rag.embeddings.mock_embedder import MockEmbedder

logger = logging.getLogger(__name__)


def get_embedder(api_key: Optional[str] = None, model: Optional[str] = None) -> BaseEmbedder:
    """
    Factory returning an initialized Embedder instance.
    Uses OpenAIEmbedder if a valid API key is present in settings or environment;
    otherwise falls back gracefully to MockEmbedder.
    """
    key = api_key or getattr(settings, "OPENAI_API_KEY", "")
    model_name = model or getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    # If key is valid and not a placeholder
    if key and key.strip() and not key.startswith("your-") and not key.startswith("<"):
        try:
            return OpenAIEmbedder(api_key=key.strip(), model=model_name)
        except Exception as e:
            logger.warning(f"Could not initialize OpenAIEmbedder ({e}), falling back to MockEmbedder.")

    logger.info("Using MockEmbedder for RAG vector embeddings (deterministic local mode).")
    return MockEmbedder()


__all__ = ["BaseEmbedder", "OpenAIEmbedder", "MockEmbedder", "get_embedder"]
