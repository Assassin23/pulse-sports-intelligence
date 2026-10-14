"""
Manual Document Source — Milestone 9.

Accepts single or batch raw documents passed from Admin UI or API requests.
"""
from typing import Iterator, List
from sports_platform.rag.ingestion.sources.base import DocumentSource
from sports_platform.rag.ingestion.pipeline import RawDocument


class ManualDocumentSource(DocumentSource):
    """Yields documents provided directly in memory."""

    def __init__(self, documents: List[RawDocument]):
        self._documents = documents

    def fetch_documents(self) -> Iterator[RawDocument]:
        for doc in self._documents:
            yield doc
