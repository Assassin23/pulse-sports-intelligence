"""
Deterministic Mock Embedder — Milestone 9.

Generates reproducible 1536-dimensional unit-normalized vectors for
offline development, unit testing, and evaluation suites without calling external APIs.
"""
import hashlib
import math
import re
from typing import List
from sports_platform.rag.embeddings.base import BaseEmbedder


class MockEmbedder(BaseEmbedder):
    """
    Deterministic pseudo-semantic embedder.
    Maps words and text hash onto a 1536-dimensional unit hypersphere.
    Similar texts containing shared vocabulary produce positive cosine similarity,
    while identical texts produce cosine similarity 1.0.
    """

    DIMENSIONS = 1536

    def __init__(self, dimensions: int = 1536):
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _hash_word_to_dimensions(self, word: str) -> List[int]:
        """Project a word to 3 distinct coordinate indices within dimension space."""
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx1 = h % self._dimensions
        idx2 = (h >> 16) % self._dimensions
        idx3 = (h >> 32) % self._dimensions
        return [idx1, idx2, idx3]

    def _embed_single(self, text: str) -> List[float]:
        vec = [0.0] * self._dimensions
        words = re.findall(r"\w+", text.lower())

        if not words:
            # Fallback for empty text: stable hash vector
            h = hashlib.sha256(text.encode("utf-8")).digest()
            for i, b in enumerate(h):
                vec[i % self._dimensions] += (b - 128) / 128.0
        else:
            for word in words:
                indices = self._hash_word_to_dimensions(word)
                for idx in indices:
                    vec[idx] += 1.0

        # Also add a slight global signature from the full text SHA-256
        full_hash = hashlib.sha256(text.encode("utf-8")).digest()
        for i, b in enumerate(full_hash[:64]):
            vec[i * (self._dimensions // 64)] += (b - 128) / 512.0

        # Normalize to unit vector: L2 norm = 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [x / norm for x in vec]
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_single(t) for t in texts]
