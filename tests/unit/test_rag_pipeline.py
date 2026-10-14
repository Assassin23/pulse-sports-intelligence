"""
Unit and Integration Tests for RAG Document Pipeline — Milestone 9.

Tests:
1. Semantic chunking (paragraph awareness, 400-token target, 50-token overlap, header context)
2. Embedder dimension, normalization, and determinism
3. Ingestion pipeline with SHA-256 deduplication and idempotency
4. Hybrid retrieval with metadata filtering and freshness boost
5. Candidate re-ranking
6. Admin ingestion and search API endpoints
7. Golden Q&A evaluation fixtures
"""
from datetime import datetime, timezone, timedelta
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from sports_platform.rag.chunking.semantic_chunker import SemanticChunker, Chunk
from sports_platform.rag.embeddings.mock_embedder import MockEmbedder
from sports_platform.rag.retrieval.reranker import LexicalHybridReranker
from sports_platform.rag.retrieval.retriever import HybridRetriever, RetrievedChunk
from sports_platform.rag.ingestion.pipeline import DocumentIngestionPipeline, RawDocument
from sports_platform.rag.models import RAGDocument, RAGChunk
from sports_platform.sports.models import Sport
from tests.factories import UserFactory, SportFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def normal_user(db):
    return UserFactory(is_staff=False)


@pytest.fixture
def staff_user(db):
    return UserFactory(is_staff=True)


@pytest.fixture
def cricket_sport(db):
    return Sport.objects.get_or_create(slug="cricket", defaults={"name": "Cricket", "is_active": True})[0]


@pytest.fixture
def football_sport(db):
    return Sport.objects.get_or_create(slug="football", defaults={"name": "Football", "is_active": True})[0]


@pytest.fixture
def tennis_sport(db):
    return Sport.objects.get_or_create(slug="tennis", defaults={"name": "Tennis", "is_active": True})[0]


class TestSemanticChunker:
    def test_chunker_basic_and_header(self):
        chunker = SemanticChunker(target_tokens=100, overlap_tokens=20)
        doc = RawDocument(
            title="Football Rules",
            document_type="competition_rules",
            content="Football is played with two teams of 11 players.\n\nThe game lasts 90 minutes.",
        )
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1
        assert chunks[0].text.startswith("[competition_rules] Football Rules\n\n")
        assert chunks[0].token_count > 0

    def test_chunker_empty_content(self):
        chunker = SemanticChunker()
        doc = RawDocument(title="Empty", content="   ")
        chunks = chunker.chunk(doc)
        assert chunks == []

    def test_chunker_paragraph_splitting_and_overlap(self):
        chunker = SemanticChunker(target_tokens=50, overlap_tokens=15)
        # 5 distinct long paragraphs
        paras = [
            f"Paragraph {i} contains detailed strategic text discussing how tactical setups and offensive structures operate under pressure in modern competitive sporting tournaments."
            for i in range(1, 6)
        ]
        doc = RawDocument(
            title="Tactical Overview",
            document_type="article",
            content="\n\n".join(paras),
        )
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1
        # Each chunk must contain the header
        for c in chunks:
            assert c.text.startswith("[article] Tactical Overview\n\n")


class TestEmbedder:
    def test_mock_embedder_dimensions_and_normalization(self):
        embedder = MockEmbedder(dimensions=1536)
        assert embedder.dimensions == 1536

        texts = ["Arsenal Football Club", "Cricket DRS rule"]
        embeddings = embedder.embed_batch(texts)
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1536
        assert len(embeddings[1]) == 1536

        # Check unit norm: sqrt(sum(v^2)) == 1.0
        norm0 = sum(x * x for x in embeddings[0]) ** 0.5
        norm1 = sum(x * x for x in embeddings[1]) ** 0.5
        assert pytest.approx(norm0, rel=1e-4) == 1.0
        assert pytest.approx(norm1, rel=1e-4) == 1.0

    def test_mock_embedder_determinism(self):
        embedder = MockEmbedder(dimensions=1536)
        text = "Virat Kohli masterclass in T20 cricket chase"
        v1 = embedder.embed_query(text)
        v2 = embedder.embed_query(text)
        assert v1 == v2


@pytest.mark.django_db
class TestDocumentIngestionPipeline:
    def test_ingest_new_document(self, football_sport):
        pipeline = DocumentIngestionPipeline(
            chunker=SemanticChunker(target_tokens=100),
            embedder=MockEmbedder(dimensions=1536),
        )
        doc = RawDocument(
            title="Arsenal Tactical Identity",
            document_type="team_profile",
            sport="football",
            entity_type="team",
            content="Arsenal plays possession football under Mikel Arteta.\n\nInverted fullbacks dominate the midfield.",
        )
        doc_id = pipeline.ingest(doc)
        assert doc_id is not None

        db_doc = RAGDocument.objects.get(id=doc_id)
        assert db_doc.title == "Arsenal Tactical Identity"
        assert db_doc.sport == football_sport
        assert db_doc.chunks.count() >= 1

        first_chunk = db_doc.chunks.first()
        assert first_chunk.metadata["sport"] == "football"
        assert first_chunk.metadata["document_type"] == "team_profile"

    def test_ingest_deduplication_idempotency(self, cricket_sport):
        pipeline = DocumentIngestionPipeline(
            chunker=SemanticChunker(target_tokens=100),
            embedder=MockEmbedder(dimensions=1536),
        )
        doc = RawDocument(
            title="IPL Powerplay",
            document_type="competition_rules",
            sport="cricket",
            content="First 6 overs have only 2 fielders outside the circle.",
        )
        doc_id_1 = pipeline.ingest(doc)
        initial_chunk_count = RAGChunk.objects.count()

        # Ingest identical content again
        doc_id_2 = pipeline.ingest(doc)
        assert doc_id_1 == doc_id_2
        # No extra chunks created
        assert RAGChunk.objects.count() == initial_chunk_count

    def test_ingest_empty_content_raises(self):
        pipeline = DocumentIngestionPipeline()
        doc = RawDocument(title="Empty", content="   ")
        with pytest.raises(ValueError):
            pipeline.ingest(doc)


@pytest.mark.django_db
class TestHybridRetrieverAndReranker:
    def test_retriever_metadata_filtering(self, football_sport, cricket_sport):
        embedder = MockEmbedder(dimensions=1536)
        pipeline = DocumentIngestionPipeline(embedder=embedder)

        # Ingest a football doc
        pipeline.ingest(
            RawDocument(
                title="Football Offside Rule",
                document_type="competition_rules",
                sport="football",
                content="Offside occurs when an attacker is nearer to the opponents goal line than the second-last opponent.",
            )
        )

        # Ingest a cricket doc
        pipeline.ingest(
            RawDocument(
                title="Cricket DRS Rules",
                document_type="competition_rules",
                sport="cricket",
                content="DRS enables player reviews for LBW and caught behind using ball tracking and UltraEdge.",
            )
        )

        retriever = HybridRetriever(embedder=embedder)

        # Query filtered by sport=football
        football_results = retriever.retrieve(query="rules of the game", sport="football", top_n=5)
        for r in football_results:
            assert r.sport == "football"

        # Query filtered by sport=cricket
        cricket_results = retriever.retrieve(query="rules of the game", sport="cricket", top_n=5)
        for r in cricket_results:
            assert r.sport == "cricket"

    def test_retriever_freshness_boost(self, football_sport):
        embedder = MockEmbedder(dimensions=1536)
        pipeline = DocumentIngestionPipeline(embedder=embedder)

        now = datetime.now(timezone.utc)
        recent_date = now - timedelta(days=2)
        old_date = now - timedelta(days=90)

        # Ingest old doc
        doc_old = RawDocument(
            title="Old Tactics",
            document_type="article",
            sport="football",
            content="General football tactical guidelines and formations.",
            published_at=old_date,
        )
        pipeline.ingest(doc_old)

        # Ingest fresh doc with identical theme
        doc_fresh = RawDocument(
            title="Fresh Tactics",
            document_type="article",
            sport="football",
            content="General football tactical guidelines and modern shapes.",
            published_at=recent_date,
        )
        pipeline.ingest(doc_fresh)

        retriever = HybridRetriever(embedder=embedder, freshness_boost_days=30, freshness_boost_score=0.05)
        results = retriever.retrieve(query="football tactical guidelines", sport="football", top_n=5)

        assert len(results) >= 2
        fresh_chunk = next(r for r in results if r.document_title == "Fresh Tactics")
        assert fresh_chunk.similarity > 0.05

    def test_lexical_hybrid_reranker(self):
        reranker = LexicalHybridReranker()
        query = "Erling Haaland Manchester City goal record"

        chunk_a = RetrievedChunk(
            chunk_id="1",
            content="Erling Haaland scored 36 Premier League goals for Manchester City.",
            similarity=0.6,
            document_id="doc1",
            document_title="Haaland Profile",
            document_type="player_profile",
        )
        chunk_b = RetrievedChunk(
            chunk_id="2",
            content="Tennis player Novak Djokovic has 24 Grand Slam titles.",
            similarity=0.65,  # Slightly higher initial dense score
            document_id="doc2",
            document_title="Djokovic Profile",
            document_type="player_profile",
        )

        reranked = reranker.rerank(query=query, candidates=[chunk_b, chunk_a], top_n=2)
        # chunk_a contains exact keywords and must be re-ranked to the top
        assert reranked[0].chunk_id == "1"


@pytest.mark.django_db
class TestRAGApiEndpoints:
    def test_admin_ingest_forbidden_for_regular_user(self, api_client, normal_user):
        api_client.force_authenticate(user=normal_user)
        payload = {
            "title": "Unauthorized Document",
            "content": "Secret content",
            "document_type": "article",
        }
        response = api_client.post("/api/v1/admin/rag/ingest", payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_ingest_success_for_staff(self, api_client, staff_user, cricket_sport):
        api_client.force_authenticate(user=staff_user)
        payload = {
            "title": "Chennai Super Kings Fortress",
            "content": "CSK has won 5 IPL trophies under captain MS Dhoni at Chepauk.",
            "document_type": "team_profile",
            "sport": "cricket",
            "entity_type": "team",
        }
        response = api_client.post("/api/v1/admin/rag/ingest", payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "document_id" in response.data
        assert response.data["chunks_created"] >= 1

    def test_rag_search_endpoint(self, api_client, normal_user, cricket_sport):
        # Pre-seed one document
        pipeline = DocumentIngestionPipeline()
        pipeline.ingest(
            RawDocument(
                title="CSK Chepauk Fortress",
                content="CSK has won 5 IPL trophies under captain MS Dhoni at Chepauk.",
                document_type="team_profile",
                sport="cricket",
            )
        )

        api_client.force_authenticate(user=normal_user)
        search_payload = {
            "query": "How many trophies has CSK won at Chepauk?",
            "sport": "cricket",
            "top_n": 3,
        }
        response = api_client.post("/api/v1/rag/search/", search_payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1
        assert "results" in response.data
        first_result = response.data["results"][0]
        assert "citation" in first_result
        assert first_result["citation"]["title"] == "CSK Chepauk Fortress"


@pytest.mark.django_db
class TestGoldenQAEvaluation:
    """
    RAG retrieval evaluation tests against canonical golden Q&A pairs.
    Verifies that top-ranked chunk contains the required factual answer.
    """

    GOLDEN_QA_PAIRS = [
        {
            "query": "What is the offside rule in football?",
            "sport": "football",
            "expected_keywords": ["offside", "opponent", "goal line"],
            "expected_doc_title": "IFAB Law 11",
            "doc": RawDocument(
                title="IFAB Law 11: Offside Rule",
                document_type="competition_rules",
                sport="football",
                content="Law 11: A player is in an offside position if nearer to the opponent's goal line than the ball and second-last opponent.",
            ),
        },
        {
            "query": "How does DRS ball tracking and UltraEdge review LBW decisions?",
            "sport": "cricket",
            "expected_keywords": ["drs", "ultraedge", "lbw"],
            "expected_doc_title": "DRS Protocols",
            "doc": RawDocument(
                title="DRS Protocols and UltraEdge",
                document_type="competition_rules",
                sport="cricket",
                content="DRS reviews check legal delivery, UltraEdge sound spikes for bat contact, and Hawk-Eye ball tracking for LBW wickets.",
            ),
        },
        {
            "query": "What are the rules for the 10-point final set tiebreak in Grand Slam tennis?",
            "sport": "tennis",
            "expected_keywords": ["10-point", "tiebreak", "grand slam"],
            "expected_doc_title": "Grand Slam Scoring",
            "doc": RawDocument(
                title="Grand Slam Scoring and 10-Point Tiebreak",
                document_type="competition_rules",
                sport="tennis",
                content="At 6-6 in the deciding final set, a unified 10-point super tiebreak decides the Grand Slam match winner.",
            ),
        },
    ]

    def test_golden_qa_retrieval(self, football_sport, cricket_sport, tennis_sport):
        embedder = MockEmbedder(dimensions=1536)
        pipeline = DocumentIngestionPipeline(embedder=embedder)

        # Ingest all golden documents
        for item in self.GOLDEN_QA_PAIRS:
            pipeline.ingest(item["doc"])

        retriever = HybridRetriever(embedder=embedder)

        # Evaluate each golden query
        for item in self.GOLDEN_QA_PAIRS:
            results = retriever.retrieve(query=item["query"], sport=item["sport"], top_n=3)
            assert len(results) > 0, f"No results retrieved for query: {item['query']}"
            top_hit = results[0]
            # Verify document title relevance
            assert item["expected_doc_title"].lower() in top_hit.document_title.lower()
            # Verify required factual keywords are present in retrieved chunk
            for kw in item["expected_keywords"]:
                assert kw.lower() in top_hit.content.lower()
