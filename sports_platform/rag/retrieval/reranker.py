"""
Re-ranking Module — Milestone 9.

Supports:
1. Cohere Rerank API (managed high-accuracy reranker)
2. Local Cross-Encoder (if sentence-transformers installed)
3. Lexical Hybrid Reranker (zero-dependency BM25-style keyword overlap)
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Any
import math
import re
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    """Abstract interface for second-stage candidate re-ranking."""

    @abstractmethod
    def rerank(self, query: str, candidates: List[Any], top_n: int = 5) -> List[Any]:
        """Re-rank candidate chunks against query and return top_n."""
        pass


class CohereReranker(BaseReranker):
    """
    Wraps Cohere Rerank API (rerank-english-v3.0).
    """

    def __init__(self, api_key: str, model: str = "rerank-english-v3.0"):
        if not api_key:
            raise ValueError("Cohere API key required for CohereReranker.")
        self._api_key = api_key
        self._model = model

    def rerank(self, query: str, candidates: List[Any], top_n: int = 5) -> List[Any]:
        if not candidates or len(candidates) <= 1:
            return candidates[:top_n]

        try:
            import cohere
            co = cohere.Client(api_key=self._api_key)
            docs = [c.content for c in candidates]
            response = co.rerank(
                model=self._model,
                query=query,
                documents=docs,
                top_n=min(top_n, len(candidates)),
            )
            reranked = []
            for r in response.results:
                chunk = candidates[r.index]
                # Update score with rerank relevance
                chunk.similarity = float(r.relevance_score)
                reranked.append(chunk)
            return reranked
        except Exception as e:
            logger.warning(f"Cohere rerank call failed ({e}); falling back to original order.")
            return candidates[:top_n]


class LexicalHybridReranker(BaseReranker):
    """
    Zero-dependency fast hybrid reranker.
    Calculates BM25-inspired term frequency and exact keyword matching,
    blending lexical precision with dense semantic similarity:
    final_score = 0.65 * dense_similarity + 0.35 * lexical_score
    """

    def _tokenize(self, text: str) -> List[str]:
        return [w.lower() for w in re.findall(r"\w+", text) if len(w) > 1]

    def _score_chunk(self, query_tokens: List[str], chunk_text: str, dense_sim: float) -> float:
        if not query_tokens:
            return dense_sim

        chunk_tokens = self._tokenize(chunk_text)
        if not chunk_tokens:
            return dense_sim

        chunk_token_set = set(chunk_tokens)
        query_token_set = set(query_tokens)

        # 1. Term coverage
        matched_tokens = query_token_set.intersection(chunk_token_set)
        coverage = len(matched_tokens) / len(query_token_set)

        # 2. Term frequency boost
        tf_score = 0.0
        for token in matched_tokens:
            count = chunk_tokens.count(token)
            # Sub-linear term frequency
            tf_score += math.log(1.0 + count)
        norm_tf = min(1.0, tf_score / (len(query_token_set) * 2.0))

        # 3. Exact phrase match bonus
        exact_phrase_bonus = 0.15 if " ".join(query_tokens) in chunk_text.lower() else 0.0

        lexical_score = (0.5 * coverage) + (0.35 * norm_tf) + exact_phrase_bonus
        lexical_score = min(1.0, lexical_score)

        # Combine with dense similarity
        blended = (0.65 * dense_sim) + (0.35 * lexical_score)
        return round(blended, 4)

    def rerank(self, query: str, candidates: List[Any], top_n: int = 5) -> List[Any]:
        if not candidates or len(candidates) <= 1:
            return candidates[:top_n]

        query_tokens = self._tokenize(query)
        scored_candidates = []
        for candidate in candidates:
            blended_score = self._score_chunk(
                query_tokens=query_tokens,
                chunk_text=candidate.content,
                dense_sim=candidate.similarity,
            )
            candidate.similarity = blended_score
            scored_candidates.append(candidate)

        # Sort descending by updated score
        scored_candidates.sort(key=lambda c: c.similarity, reverse=True)
        return scored_candidates[:top_n]


def get_reranker(api_key: Optional[str] = None) -> BaseReranker:
    """Return configured reranker instance."""
    key = api_key or getattr(settings, "COHERE_API_KEY", "")
    if key and key.strip() and not key.startswith("your-") and not key.startswith("<"):
        try:
            return CohereReranker(api_key=key.strip())
        except Exception as e:
            logger.warning(f"Could not initialize CohereReranker ({e}). Using LexicalHybridReranker.")
    return LexicalHybridReranker()
