"""
Document Source Base Class — Milestone 9.
"""
from abc import ABC, abstractmethod
from typing import Iterator
from sports_platform.rag.ingestion.pipeline import RawDocument


class DocumentSource(ABC):
    """Abstract interface for external/internal document sources."""

    @abstractmethod
    def fetch_documents(self) -> Iterator[RawDocument]:
        """Yield RawDocument items ready for ingestion."""
        pass
