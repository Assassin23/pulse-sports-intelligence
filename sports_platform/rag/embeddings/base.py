"""
Base Embedder Interface — Milestone 9.
"""
from abc import ABC, abstractmethod
from typing import List


class BaseEmbedder(ABC):
    """Abstract base class for RAG text embedding providers."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the vector dimensionality (e.g. 1536)."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of text strings into vectors."""
        pass

    def embed_query(self, text: str) -> List[float]:
        """Convenience method to embed a single query text."""
        results = self.embed_batch([text])
        if results and len(results) > 0:
            return results[0]
        return [0.0] * self.dimensions
