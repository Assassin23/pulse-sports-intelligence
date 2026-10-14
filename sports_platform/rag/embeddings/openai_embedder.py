"""
OpenAI Embedder Implementation — Milestone 9.

Wraps OpenAI text-embedding-3-small (1536 dimensions) with batching
and exponential backoff retry on rate limits.
"""
from typing import List, Optional
import time
import logging
from sports_platform.rag.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class OpenAIEmbedder(BaseEmbedder):
    """
    Production embedder using OpenAI text-embedding-3-small.
    - Dimensions: 1536
    - Batch size: 100 chunks per API call
    - Retries: 3 attempts with exponential backoff
    """

    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    BATCH_SIZE = 100

    def __init__(self, api_key: str, model: Optional[str] = None):
        if not api_key:
            raise ValueError("OpenAI API key must be provided to OpenAIEmbedder.")
        if OpenAI is None:
            raise ImportError("openai package is not installed. Please install openai>=1.50.0")

        self.model = model or self.MODEL
        self._client = OpenAI(api_key=api_key)

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            embeddings = self._embed_with_retry(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def _embed_with_retry(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        for attempt in range(max_retries):
            try:
                response = self._client.embeddings.create(
                    model=self.model,
                    input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        f"OpenAI embedding call failed (attempt {attempt + 1}/{max_retries}), retrying in {wait}s: {e}"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"OpenAI embedding call permanently failed after {max_retries} attempts: {e}")
                    raise
        return []
