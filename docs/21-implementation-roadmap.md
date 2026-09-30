# 21. Implementation Roadmap

## Overview

Each milestone produces a working, deployable increment. Later milestones build on earlier ones.

**Conventions:**
- ✅ = Deliverable
- 🔴 = Blocking dependency
- Estimated effort is for **one senior engineer** working full-time.

---

## Milestone 1: Foundation — Auth + User Preferences

**Duration:** ~2 weeks  
**Goal:** Users can register, authenticate, and set their sport/team preferences.

### Deliverables
- ✅ Django project scaffolding (modular monolith structure)
- ✅ PostgreSQL schema: `users`, `refresh_tokens`, `sports`, `countries`, `teams`, `competitions`, `players`, `user_sport_preferences`, `user_followed_entities`
- ✅ JWT authentication (register, login, refresh, logout, token blacklist in Redis)
- ✅ `/api/v1/auth/*` endpoints
- ✅ `/api/v1/users/me/preferences` GET + PUT + follow/unfollow
- ✅ Max-3-sports validation in preferences service
- ✅ Unit tests for auth + preferences logic
- ✅ Docker Compose with PostgreSQL + Redis + Django
- ✅ `.env.example` with all required variables
- ✅ `seed_sports` management command (sports, countries)

**Dependencies:** None.

---

## Milestone 2: Sports Reference Data + Provider Integration

**Duration:** ~2 weeks  
**Goal:** First external provider connected; fixtures discoverable.

### Deliverables
- ✅ `SportsDataProvider` abstract interface
- ✅ `ApiFootballAdapter` (or first cricket provider) concrete implementation
- ✅ `ProviderRegistry` + `CircuitBreaker`
- ✅ Provider entity mapping table + dedup logic
- ✅ `ProviderEntityMapping` service (internal ID resolution)
- ✅ VCR cassette tests for provider adapter
- ✅ Sports search endpoints: `/api/v1/sports/{slug}/teams`, `/api/v1/sports/{slug}/competitions`
- ✅ `seed_fixtures` command using real provider data

**Dependencies:** 🔴 Milestone 1 (user + sports models)

---

## Milestone 3: Kafka + Match Discovery Pipeline

**Duration:** ~2 weeks  
**Goal:** Fixtures discovered by ingestion worker, stored in DB, queryable via API.

### Deliverables
- ✅ Kafka (Docker Compose, KRaft mode)
- ✅ Kafka topic creation management command
- ✅ `KafkaEventProducer` (singleton, typed publish methods)
- ✅ `BaseKafkaConsumer` (manual commit, retry, DLQ, dedup)
- ✅ `run_kafka_consumers` management command
- ✅ `sports.match.discovered` event contract
- ✅ `SportsIngestionWorker` + Celery Beat schedule
- ✅ `MatchProcessorConsumer` (match.discovered → PostgreSQL)
- ✅ `provider_entity_mappings` resolution
- ✅ `GET /api/v1/matches/upcoming` endpoint
- ✅ Kafka UI in Docker Compose
- ✅ Kafka integration tests (testcontainers)

**Dependencies:** 🔴 Milestone 2 (provider + sports data)

---

## Milestone 4: Live Match Processing + Redis State

**Duration:** ~2 weeks  
**Goal:** Live scores and events flowing through Kafka into Redis and PostgreSQL.

### Deliverables
- ✅ `sports.match.started`, `sports.score.updated`, `sports.match.event`, `sports.match.completed` events
- ✅ `ScoreProcessorConsumer` (idempotent, sequence check, Lua script)
- ✅ `EventProcessorConsumer` (dedup on event_sequence)
- ✅ Redis key schema: `match:score:*`, `match:events:recent:*`, `matches:live`
- ✅ Redis integration tests
- ✅ `GET /api/v1/matches/live` served from Redis (fast path)
- ✅ `GET /api/v1/matches/{id}` with score + recent events
- ✅ `GET /api/v1/matches/{id}/events` paginated from PostgreSQL
- ✅ Ingestion polling loop for live matches
- ✅ `simulate_live_match` management command (local testing)
- ✅ Freshness indicator (`data_freshness_seconds`) in API responses

**Dependencies:** 🔴 Milestone 3 (Kafka pipeline)

---

## Milestone 5: Personalized Feed

**Duration:** ~1 week  
**Goal:** Users see a personalized feed based on their preferences.

### Deliverables
- ✅ `FeedService` (assembles feed from followed entities + live matches)
- ✅ Feed Redis cache (`feed:{user_id}`, TTL 5 min)
- ✅ `sports.user.preference.updated` Kafka event
- ✅ `FeedInvalidationConsumer` (cache bust on preference change)
- ✅ `GET /api/v1/feed` endpoint (cursor-paginated)
- ✅ Unit tests for feed assembly logic

**Dependencies:** 🔴 Milestone 4 (live match state in Redis)

---

## Milestone 6: WebSocket Live Updates

**Duration:** ~2 weeks  
**Goal:** Clients receive real-time score and event updates without polling.

### Deliverables
- ✅ FastAPI WebSocket gateway service
- ✅ Redis Pub/Sub integration (score processor publishes, gateway subscribes)
- ✅ `ws://gateway/ws/match/{id}` — initial state + streaming updates
- ✅ `ws://gateway/ws/feed` — personal channel
- ✅ Subscription management in Redis (`ws:match:subs:*`, `ws:conn:*`)
- ✅ WebSocket authentication (JWT query param)
- ✅ Reconnection handling (client sends `?since=` on reconnect)
- ✅ WebSocket tests (asyncio + websockets library)
- ✅ Prometheus metrics: active connections, messages sent

**Dependencies:** 🔴 Milestone 4 (Redis Pub/Sub publish from processors)

---

## Milestone 7: Odds Ingestion

**Duration:** ~1 week  
**Goal:** Current odds displayed in match detail and feed; odds history tracked.

### Deliverables
- ✅ `OddsDataProvider` interface + first odds adapter
- ✅ Odds change fingerprinting (skip unchanged odds)
- ✅ `sports.odds.updated` Kafka event
- ✅ `OddsProcessorConsumer`
- ✅ PostgreSQL: `match_odds_current`, `match_odds_history`
- ✅ Redis: `match:odds:*`, `match:odds:history:*`
- ✅ `GET /api/v1/matches/{id}/odds` endpoint
- ✅ Odds in match detail and feed responses
- ✅ Odds disclaimer in all API responses
- ✅ Celery Beat: odds polling schedule

**Dependencies:** 🔴 Milestone 3 (Kafka pipeline), Milestone 4 (provider framework)

---

## Milestone 8: Notifications

**Duration:** ~2 weeks  
**Goal:** Users receive real-time and push notifications for followed match events.

### Deliverables
- ✅ `notifications.requested` Kafka event
- ✅ `NotificationProcessorConsumer` (match event → affected users lookup)
- ✅ `NotificationDeliveryWorker` (WebSocket + push)
- ✅ FCM integration for push notifications
- ✅ Notification rate limiting (max 3/type/match/5min)
- ✅ Upcoming match reminders (Celery Beat, 15 min before kickoff)
- ✅ `user_notification_preferences` model + API
- ✅ `GET/PUT /api/v1/users/me/notifications`
- ✅ `notification_log` table + admin view
- ✅ Unit tests for fanout logic

**Dependencies:** 🔴 Milestone 4 (match events), Milestone 6 (WebSocket personal channel)

---

## Milestone 9: RAG Document Pipeline

**Duration:** ~2 weeks  
**Goal:** Knowledge base populated; retrieval working and tested.

### Deliverables
- ✅ pgvector extension enabled in PostgreSQL
- ✅ `RAGDocument`, `RAGChunk` models + HNSW index
- ✅ `DocumentIngestionPipeline` (hash dedup, chunk, embed, store)
- ✅ `SemanticChunker` (paragraph-aware, with overlap)
- ✅ `OpenAIEmbedder` (batch, retry)
- ✅ `HybridRetriever` (vector search + metadata filter)
- ✅ `CohereReranker` (or cross-encoder)
- ✅ Admin API: `POST /api/v1/admin/rag/ingest` (data_admin role)
- ✅ `seed_rag_docs` management command (loads sample team/player/rules docs)
- ✅ RAG retrieval evaluation tests (golden Q&A pairs)

**Dependencies:** 🔴 Milestone 1 (PostgreSQL), pgvector installed

---

## Milestone 10: LangGraph AI Match Assistant

**Duration:** ~3 weeks  
**Goal:** Users can ask natural language questions about any match.

### Deliverables
- ✅ LangGraph graph definition + `AssistantState`
- ✅ All graph nodes: intent_classifier, data_planner, backend_tools, rag_retrieval, synthesizer, validator, responder
- ✅ All backend tools: `get_live_score`, `get_match_events`, `get_team_stats`, `get_standings`, `get_recent_matches`
- ✅ Tool error handling (structured error return, not exceptions)
- ✅ Prompt injection detection
- ✅ Conversation persistence (`AIConversation`, `AIMessage`)
- ✅ `POST /api/v1/ai/matches/{id}/ask`
- ✅ `GET /api/v1/ai/matches/{id}/conversations`
- ✅ AI rate limiting (20 req/hour/user)
- ✅ Citations in response
- ✅ Token usage logging to `ai_messages`
- ✅ AI tests (tool contracts, graph execution, injection defense)

**Dependencies:** 🔴 Milestone 9 (RAG), Milestone 4 (live data tools)

---

## Milestone 11: Observability

**Duration:** ~1 week  
**Goal:** Full observability in place before load testing.

### Deliverables
- ✅ Prometheus metrics (all defined in observability doc)
- ✅ Grafana dashboards (API health, Kafka, AI, Provider)
- ✅ Loki log aggregation (Grafana Loki driver in Docker Compose)
- ✅ OpenTelemetry instrumentation (Django, PostgreSQL, Redis, httpx)
- ✅ Structlog JSON logging across all services
- ✅ Kafka consumer lag collection + Grafana panel
- ✅ Alert rules defined in Grafana
- ✅ `/health` and `/health/ready` endpoints

**Dependencies:** All services must be running (Milestone 6+)

---

## Milestone 12: Load Testing + Performance Tuning

**Duration:** ~1 week  
**Goal:** System validated at target scale (1K concurrent users, 100 live matches).

### Deliverables
- ✅ Locust load test suite
- ✅ API p99 < 200ms at 1K concurrent users
- ✅ 1K concurrent WebSocket connections stable (no memory leak)
- ✅ Kafka consumer lag < 500ms at peak
- ✅ Feed cache hit rate > 80%
- ✅ Redis score read p99 < 5ms
- ✅ AI assistant p95 < 10s
- ✅ Database query optimization (EXPLAIN ANALYZE on slow queries)
- ✅ Document load test findings + any fixes applied

**Dependencies:** 🔴 Milestone 11 (observability required to interpret results)

---

## Milestone 13: Production Hardening

**Duration:** ~1 week  
**Goal:** System is production-ready, secure, and documented.

### Deliverables
- ✅ Production settings (DEBUG=false, security headers, HTTPS, CORS)
- ✅ RSA keypair for JWT (replace HS256 with RS256)
- ✅ Secrets in AWS Secrets Manager / environment secrets
- ✅ GitHub Actions CI/CD pipeline (test → build → deploy)
- ✅ PostgreSQL RDS setup + automated backups
- ✅ Redis ElastiCache setup
- ✅ Kafka MSK or self-hosted 3-broker cluster
- ✅ Nginx production config (HTTPS, rate limits, WebSocket)
- ✅ Sentry error tracking integration
- ✅ GDPR data export/deletion endpoints
- ✅ Pre-commit hooks (ruff, black, detect-secrets, mypy)
- ✅ Production runbook (in `docs/runbook.md`)

**Dependencies:** 🔴 All prior milestones

---

## Summary Timeline

| Milestone | Duration | Cumulative |
|---|---|---|
| 1. Auth + Preferences | 2 weeks | 2 weeks |
| 2. Provider Integration | 2 weeks | 4 weeks |
| 3. Kafka + Match Discovery | 2 weeks | 6 weeks |
| 4. Live Match + Redis | 2 weeks | 8 weeks |
| 5. Personalized Feed | 1 week | 9 weeks |
| 6. WebSocket | 2 weeks | 11 weeks |
| 7. Odds | 1 week | 12 weeks |
| 8. Notifications | 2 weeks | 14 weeks |
| 9. RAG | 2 weeks | 16 weeks |
| 10. AI Match Assistant | 3 weeks | 19 weeks |
| 11. Observability | 1 week | 20 weeks |
| 12. Load Testing | 1 week | 21 weeks |
| 13. Production Hardening | 1 week | 22 weeks |

**Total: ~5.5 months for one senior engineer** to a production-ready system.
