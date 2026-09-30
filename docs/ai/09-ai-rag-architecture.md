# 9. AI & RAG Architecture

## 9.1 Architecture Overview

The AI layer has two clearly separated components:

| Component | Purpose | Data Source |
|---|---|---|
| **Backend Tools** | Live scores, events, statistics, standings | Redis → PostgreSQL (deterministic, authoritative) |
| **RAG System** | Team history, rules, player profiles, articles | Vector database (pgvector) |

**Critical principle:** The LLM is **never** the source of truth for live or current data. All live/current data comes from deterministic backend tools. The LLM's role is synthesis, reasoning, and natural language generation.

---

## 9.2 What Goes Into RAG vs Backend Tools

### RAG (Vector Search — Contextual Knowledge)
- Team history and background information
- Competition rules (IPL Powerplay rules, Football offside rule, etc.)
- Player profiles and career highlights
- Historical match summaries and statistics
- Sports terminology and glossary
- News articles about teams, players, competitions

### Backend Tools (Deterministic — Live Data)
- Current match score
- Live match events (last 30 minutes)
- Current team standings/points table
- Recent H2H results (last 5 matches)
- Live match statistics (possession, shots, run rate, etc.)

---

## 9.3 RAG Document Pipeline

### Step 1: Document Ingestion

```python
# sports_platform/rag/ingestion/pipeline.py

from dataclasses import dataclass
from typing import List, Optional
import hashlib


@dataclass
class RawDocument:
    title: str
    content: str
    source_url: Optional[str]
    document_type: str  # 'team_profile', 'player_profile', 'competition_rules', 'article'
    sport: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[str]
    published_at: Optional[str]
    language: str = "en"


class DocumentIngestionPipeline:
    def __init__(self, chunker, embedder, db):
        self._chunker = chunker
        self._embedder = embedder
        self._db = db

    def ingest(self, document: RawDocument) -> str:
        """Returns document_id on success."""
        
        # 1. Compute content hash for deduplication
        content_hash = hashlib.sha256(document.content.encode()).hexdigest()
        
        # 2. Check if already ingested
        existing = self._db.get_document_by_hash(content_hash)
        if existing:
            return existing.id  # Idempotent: already processed

        # 3. Persist document record
        doc_id = self._db.create_document({
            "title": document.title,
            "source_url": document.source_url,
            "document_type": document.document_type,
            "sport": document.sport,
            "entity_type": document.entity_type,
            "entity_id": document.entity_id,
            "content_hash": content_hash,
            "raw_content": document.content,
            "published_at": document.published_at,
        })

        # 4. Chunk the document
        chunks = self._chunker.chunk(document)

        # 5. Generate embeddings (batch for efficiency)
        texts = [c.text for c in chunks]
        embeddings = self._embedder.embed_batch(texts)

        # 6. Store chunks with embeddings
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            self._db.create_chunk({
                "document_id": doc_id,
                "chunk_index": i,
                "content": chunk.text,
                "token_count": chunk.token_count,
                "embedding": embedding,
                "metadata": {
                    "document_type": document.document_type,
                    "sport": document.sport,
                    "entity_type": document.entity_type,
                    "entity_id": document.entity_id,
                    "title": document.title,
                    "published_at": document.published_at,
                },
            })

        return doc_id
```

---

### Step 2: Chunking Strategy

```python
# sports_platform/rag/chunking/semantic_chunker.py

from typing import List
from dataclasses import dataclass
import tiktoken


@dataclass
class Chunk:
    text: str
    token_count: int


class SemanticChunker:
    """
    Chunking strategy:
    - Target chunk size: 400 tokens
    - Overlap: 50 tokens (preserves context at chunk boundaries)
    - Split on: paragraphs first, then sentences, then tokens
    - Preserve metadata headers in each chunk
    """
    
    TARGET_TOKENS = 400
    OVERLAP_TOKENS = 50

    def __init__(self, model: str = "text-embedding-3-small"):
        self._encoder = tiktoken.encoding_for_model(model)

    def chunk(self, document) -> List[Chunk]:
        """Split document into overlapping chunks."""
        
        # Prepend context header to every chunk for retrieval quality
        header = f"[{document.document_type}] {document.title}\n\n"
        paragraphs = document.content.split("\n\n")
        
        chunks = []
        current_tokens = []
        current_text = [header]
        
        for paragraph in paragraphs:
            para_tokens = self._encoder.encode(paragraph)
            
            if len(current_tokens) + len(para_tokens) > self.TARGET_TOKENS:
                if current_text:
                    text = "\n\n".join(current_text)
                    chunks.append(Chunk(
                        text=text,
                        token_count=len(self._encoder.encode(text))
                    ))
                
                # Start new chunk with overlap
                overlap_text = " ".join(current_text[-1].split()[-self.OVERLAP_TOKENS:])
                current_text = [header, overlap_text]
                current_tokens = self._encoder.encode(overlap_text)
            
            current_text.append(paragraph)
            current_tokens.extend(para_tokens)
        
        if current_text:
            text = "\n\n".join(current_text)
            chunks.append(Chunk(text=text, token_count=len(self._encoder.encode(text))))
        
        return chunks
```

---

### Step 3: Embeddings

```python
# sports_platform/rag/embeddings/openai_embedder.py

from openai import OpenAI
from typing import List
import time
import logging

logger = logging.getLogger(__name__)


class OpenAIEmbedder:
    """
    Wraps OpenAI text-embedding-3-small.
    Batch size: 100 chunks per API call (max allowed).
    Retry with exponential backoff on rate limits.
    """
    
    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    BATCH_SIZE = 100

    def __init__(self, api_key: str):
        self._client = OpenAI(api_key=api_key)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        all_embeddings = []
        
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            embeddings = self._embed_with_retry(batch)
            all_embeddings.extend(embeddings)
        
        return all_embeddings

    def _embed_with_retry(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        for attempt in range(max_retries):
            try:
                response = self._client.embeddings.create(
                    model=self.MODEL,
                    input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"Embedding failed, retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
```

---

### Step 4: Retrieval

```python
# sports_platform/rag/retrieval/retriever.py

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    content: str
    similarity: float
    document_id: str
    document_title: str
    document_type: str
    sport: Optional[str]
    entity_id: Optional[str]
    source_url: Optional[str]
    published_at: Optional[str]


class HybridRetriever:
    """
    Retrieval strategy:
    1. Dense retrieval: ANN vector search via pgvector (HNSW index)
    2. Metadata filtering: filter by sport, entity_type, entity_id if known
    3. Re-ranking: cross-encoder re-ranks top-k candidates → top-n final
    4. Freshness boost: more recent documents get a small score bonus
    """

    TOP_K_CANDIDATES = 20  # Retrieve 20 for re-ranking
    TOP_N_FINAL = 5         # Return top 5 after re-ranking

    def __init__(self, db, embedder, reranker):
        self._db = db
        self._embedder = embedder
        self._reranker = reranker

    def retrieve(
        self,
        query: str,
        sport: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        # 1. Embed the query
        query_embedding = self._embedder.embed_batch([query])[0]

        # 2. Build metadata filter
        filters = {}
        if sport:
            filters["sport"] = sport
        if entity_id:
            filters["entity_id"] = entity_id

        # 3. Vector similarity search (pgvector HNSW ANN)
        candidates = self._db.vector_search(
            embedding=query_embedding,
            filters=filters,
            limit=self.TOP_K_CANDIDATES,
        )

        # 4. Re-rank candidates
        if len(candidates) <= self.TOP_N_FINAL:
            return candidates[:self.TOP_N_FINAL]

        reranked = self._reranker.rerank(query, candidates)
        return reranked[:self.TOP_N_FINAL]
```

---

### Step 5: Re-ranking

```python
# sports_platform/rag/retrieval/reranker.py

# Option A: Cross-encoder re-ranking (local, fast)
# Uses a small cross-encoder model like cross-encoder/ms-marco-MiniLM-L-6-v2
# Scores (query, chunk) pairs and re-orders by score

# Option B: Cohere Rerank API (managed, high quality)
# POST https://api.cohere.ai/rerank

class CohereReranker:
    def rerank(self, query: str, chunks: list) -> list:
        import cohere
        co = cohere.Client(api_key=self._api_key)
        response = co.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=[c.content for c in chunks],
            top_n=5,
        )
        return [chunks[r.index] for r in response.results]
```

---

## 9.4 Vector Database Schema

Using **pgvector** as the vector database (PostgreSQL extension) — avoids introducing a separate infrastructure component:

```sql
-- Already defined in Database Design section
CREATE TABLE rag_chunks (
    id          UUID PRIMARY KEY,
    document_id UUID REFERENCES rag_documents(id),
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    token_count INTEGER,
    embedding   vector(1536),   -- pgvector
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast ANN search
CREATE INDEX idx_rag_chunks_embedding
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Example query: find top 20 similar chunks filtered by sport
SELECT
    c.id,
    c.content,
    1 - (c.embedding <=> $1::vector) AS similarity,
    d.title,
    d.source_url,
    d.document_type,
    c.metadata
FROM rag_chunks c
JOIN rag_documents d ON d.id = c.document_id
WHERE c.metadata->>'sport' = $2
  AND d.is_active = TRUE
ORDER BY c.embedding <=> $1::vector
LIMIT 20;
```

---

## 9.5 Document Freshness Strategy

- Each `rag_chunk.metadata` includes `published_at`.
- Retriever applies a **freshness boost**: chunks published in the last 30 days get `similarity += 0.05`.
- Periodic **re-ingestion jobs** re-process updated team profiles and competition info.
- Documents with `published_at` > 1 year ago and `document_type = 'article'` are flagged as stale.

---

## 9.6 Citations

Every RAG result includes source metadata for transparency:

```json
// Included in AI message response
"sources": [
  {
    "title": "Royal Challengers Bengaluru - Team Profile",
    "document_type": "team_profile",
    "source_url": "https://internal.wiki/rcb",
    "published_at": "2026-09-01",
    "relevance": 0.92
  }
]
```
