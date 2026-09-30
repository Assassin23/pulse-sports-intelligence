# 22. Architectural Decisions & Trade-offs

---

## ADR-001: Django Modular Monolith as Core Architecture

**Decision:** Build the core backend as a Django modular monolith (single deployed unit with clearly bounded internal apps), not a microservices system.

**Reason:** The initial team is one engineer. A microservices system introduces enormous operational overhead: separate deployments, inter-service networking, distributed tracing across service boundaries, and testing complexity. The functional requirements do not justify microservices at this scale.

**Alternatives:**
- Full microservices from day one (e.g., separate services for users, matches, odds, notifications, AI)
- Serverless functions

**Trade-offs:**
- 👍 Simpler deployment, debugging, and operations.
- 👍 Refactoring within the monolith is fast (no API versioning, no network calls).
- 👍 Single Django process means no inter-service latency for within-monolith calls.
- 👎 As the team grows, a large monolith becomes harder to separate. Mitigated by strict Django app boundaries from day one.
- 👎 Cannot independently scale individual domains (e.g., only scale the AI module). Mitigated by the Kafka consumers and WebSocket gateway being separate.

---

## ADR-002: FastAPI WebSocket Gateway as a Separate Service

**Decision:** Run the WebSocket gateway as a **separate FastAPI service**, not inside Django.

**Reason:** Django WSGI/ASGI workers are designed for short-lived request/response cycles. Managing thousands of persistent WebSocket connections inside Django workers is inefficient and requires careful ASGI worker tuning. FastAPI's async-native model with `asyncio` handles long-lived connections with far lower memory overhead.

**Alternatives:**
- Django Channels (ASGI, WebSockets inside Django)
- Server-Sent Events (SSE) instead of WebSockets
- Third-party WebSocket service (Ably, Pusher)

**Trade-offs:**
- 👍 FastAPI + uvicorn handles 5K+ concurrent WebSocket connections per instance efficiently.
- 👍 Gateway is stateless (all state in Redis), so horizontal scaling is trivial.
- 👎 An additional service to deploy, monitor, and version.
- 👎 JWT verification logic must be shared between Django and the gateway (solved via shared public key for RS256 verification).

---

## ADR-003: Kafka as Event Backbone (Not Direct DB Writes from Ingestion)

**Decision:** Ingestion workers publish to Kafka; consumers process and write to DB/Redis. Ingestion workers do NOT write directly to PostgreSQL or Redis.

**Reason:** Decoupling ingestion from processing provides:
1. **Backpressure handling:** If DB is slow, Kafka buffers; ingestion continues.
2. **Reprocessability:** Events can be replayed from Kafka after code fixes.
3. **Multiple consumers:** The same event can drive score processing, notification processing, and fan-out independently.
4. **Fault isolation:** A bug in the notification processor doesn't affect score processing.

**Alternatives:**
- Ingestion workers write directly to PostgreSQL and Redis (simpler, fewer moving parts)
- Use Celery tasks instead of Kafka

**Trade-offs:**
- 👍 True decoupling, replayability, multiple independent consumers.
- 👍 Kafka's partitioning model provides natural ordering per match.
- 👎 Adds Kafka as a required infrastructure dependency (increased operational complexity).
- 👎 End-to-end latency has an extra hop (Kafka publish → consumer).
- ⚠️ Celery alternative: valid at small scale but lacks replay, ordering guarantees, and consumer group semantics.

---

## ADR-004: pgvector for Vector Storage (Not a Dedicated Vector DB)

**Decision:** Use **pgvector** (PostgreSQL extension) as the vector database for RAG, rather than a dedicated vector database (Pinecone, Weaviate, Qdrant).

**Reason:**
1. Eliminates an entire additional infrastructure component.
2. Metadata filtering, joins with `rag_documents`, and transactional consistency are handled natively.
3. The RAG corpus size is modest (< 1M chunks at this scale). pgvector's HNSW index handles this with sub-100ms query times.
4. One engineer can manage one database, not two.

**Alternatives:**
- Pinecone (managed, no ops, higher cost)
- Qdrant (excellent, but another service to run)
- Weaviate (full-featured, more complex)

**Trade-offs:**
- 👍 Zero new infrastructure; pgvector is just a PostgreSQL extension.
- 👍 Transactional consistency between `rag_documents` and `rag_chunks` (foreign key).
- 👍 Rich metadata filtering via standard SQL.
- 👎 Not as feature-rich as dedicated vector DBs (no native re-ranking, no multi-modal).
- 👎 At very large scale (100M+ vectors), dedicated vector DBs outperform. Migrate when needed.

---

## ADR-005: Redis Pub/Sub for WebSocket Fan-out (Not Kafka)

**Decision:** Use Redis Pub/Sub for the final fan-out step (processor → WebSocket gateway → clients), not Kafka.

**Reason:** The WebSocket gateway needs to receive events in milliseconds and fan-out to connected clients. Kafka consumer polling introduces unnecessary latency for this final delivery step. Redis Pub/Sub delivers messages in < 1ms between publisher and subscriber within the same cluster.

**Alternatives:**
- Kafka consumer in the WebSocket gateway
- Redis Streams (durable, consumer groups)

**Trade-offs:**
- 👍 Sub-millisecond delivery from processor to gateway.
- 👍 Simple API for subscribe/unsubscribe.
- 👎 Fire-and-forget: messages are lost if the gateway is down (client must reconnect and re-fetch via REST).
- 👎 Not durable: if all gateway instances disconnect momentarily, messages are lost. Acceptable because the event is also in Kafka (replayable) and Redis (latest state is always available).
- ⚠️ At very high scale (>10K subs per match), consider Redis Streams for consumer groups.

---

## ADR-006: RS256 JWT (Asymmetric) Instead of HS256 (Symmetric)

**Decision:** Use RSA-256 (asymmetric) for JWT signing.

**Reason:** The WebSocket gateway is a separate service and must verify JWT tokens. With HS256 (symmetric), the secret key must be shared with every service that verifies tokens — a security risk. With RS256, only the signing service (Django) holds the private key; all verifiers use the public key.

**Alternatives:**
- HS256 with shared secret (simpler but secret must be distributed)
- OAuth2 with separate identity provider (overkill for initial scale)

**Trade-offs:**
- 👍 Private key stays in Django API only. All other services verify with public key.
- 👍 Easy key rotation (deploy new verifying key, then new signing key).
- 👎 Slightly slower than HS256 (RSA operations are more expensive). Negligible at this scale.

---

## ADR-007: Celery for Async Tasks (Not a Separate Task Queue Service)

**Decision:** Use Celery with Redis as the broker for async tasks (notifications, RAG ingestion, AI calls).

**Reason:** Celery is battle-tested, deeply integrated with Django, and handles scheduled tasks (Celery Beat) well. The team already runs Redis. Adding a separate task queue (RabbitMQ, SQS) would increase operational complexity without meaningful benefit.

**Alternatives:**
- RabbitMQ as broker (more durable, but another service)
- Django-Q (simpler, less featured)
- AWS SQS (managed, good at scale, but vendor lock-in)

**Trade-offs:**
- 👍 Single Redis instance doubles as cache + task broker.
- 👍 Celery Beat handles scheduling without a separate cron service.
- 👎 Redis as Celery broker has lower durability guarantees than RabbitMQ (task loss on Redis restart without AOF). Mitigated by enabling AOF on the auth/task Redis instance.

---

## ADR-008: LangGraph for AI Orchestration (Not Simple Chain or Agent)

**Decision:** Use LangGraph for the AI Match Assistant, not a simple LLMChain or a ReAct agent.

**Reason:**
1. The assistant workflow requires conditional branching (route to different tools based on intent).
2. Parallel tool execution (backend tools + RAG retrieval concurrently).
3. A validation step after synthesis (factual grounding check).
4. Explicit state management between nodes (conversation history, tool results, sources).
5. LangGraph provides all of this with explicit, debuggable graph structure.

**Alternatives:**
- ReAct agent (simpler, but less control over parallelism and validation)
- Fixed LLM chain (no tool calling, no adaptive routing)
- Custom async orchestrator

**Trade-offs:**
- 👍 Explicit graph makes the workflow auditable and testable at each node.
- 👍 Parallel node execution reduces AI latency significantly (tools + RAG in parallel).
- 👍 State is serializable → conversation can be resumed.
- 👎 LangGraph has a learning curve and is a significant dependency.
- 👎 More complex than a simple chain, which may be sufficient for basic questions.

---

## ADR-009: No Automated Betting or Wagering Functionality

**Decision:** Odds data is stored and displayed as **informational content only**. No bet placement, odds comparison, or gambling functionality will be implemented.

**Reason:** Legal, regulatory, and ethical compliance. Gambling services require licensing in most jurisdictions. The platform's purpose is sports intelligence, not gambling.

**Alternatives:**
- Integrate with betting exchanges (Betfair API)
- Offer odds comparison features

**Trade-offs:**
- 👍 No regulatory licensing required for odds display.
- 👍 Odds disclaimer in all API responses makes intent clear.
- 👎 Potential revenue stream foregone.

---

## ADR-010: Provider Interface Abstraction from Day One

**Decision:** All external provider integrations go through a `SportsDataProvider` abstract interface. Business logic never calls provider APIs directly.

**Reason:**
1. Provider APIs change frequently (endpoints, authentication, response formats).
2. Switching or adding providers must not require changes to core business logic.
3. Enables multi-provider failover without architecture changes.
4. Simplifies testing (mock the provider interface, not HTTP calls).

**Alternatives:**
- Hardcode first provider (faster initially, painful to change later)
- Use a third-party sports data aggregator (single endpoint, handles normalization)

**Trade-offs:**
- 👍 Swapping providers is a new adapter + registration, no business logic changes.
- 👍 Enables provider-specific test mocking via VCR cassettes.
- 👎 Initial abstraction layer adds a few hours of upfront design time.
- 👎 If using a managed aggregator, this abstraction may be less valuable.
