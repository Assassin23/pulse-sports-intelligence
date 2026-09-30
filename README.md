# Sports Intelligence Platform — System Design

> Production-grade personalized real-time sports intelligence platform.  
> Design authored: 2026-09-30

---

## Document Index

| # | Document | Description |
|---|----------|-------------|
| 1 | [Overview & Requirements](docs/01-overview-and-requirements.md) | Executive summary, functional & non-functional requirements |
| 2 | [High-Level Architecture](docs/architecture/02-high-level-architecture.md) | System diagram, service boundaries, module responsibilities |
| 3 | [Event-Driven Architecture](docs/architecture/03-event-driven-architecture.md) | Kafka topics, event contracts, partitioning, DLQ strategy |
| 4 | [Database Design](docs/data-model/04-database-design.md) | PostgreSQL schema, indexes, constraints |
| 5 | [Redis Design](docs/data-model/05-redis-design.md) | Keys, data structures, TTLs, real-time state |
| 6 | [External Provider Architecture](docs/architecture/06-provider-architecture.md) | Provider abstraction, adapters, fallback |
| 7 | [Real-Time Architecture](docs/architecture/07-realtime-architecture.md) | WebSocket flow, fan-out, reconnection, ordering |
| 8 | [Odds Architecture](docs/architecture/08-odds-architecture.md) | Odds ingestion, normalization, history tracking |
| 9 | [AI & RAG Architecture](docs/ai/09-ai-rag-architecture.md) | Document pipeline, embeddings, retrieval, reranking |
| 10 | [LangGraph Workflow](docs/ai/10-langgraph-workflow.md) | Agent graph, tools, nodes, transitions |
| 11 | [API Design](docs/api/11-api-design.md) | REST endpoints, request/response examples |
| 12 | [Authentication & Security](docs/api/12-auth-and-security.md) | AuthN, AuthZ, RBAC, rate limiting, audit logs |
| 13 | [Notifications](docs/architecture/13-notifications.md) | Match events, push, WebSocket, Kafka flow |
| 14 | [Reliability & Failure Handling](docs/infrastructure/14-reliability.md) | Retries, circuit breakers, DLQs, graceful degradation |
| 15 | [Observability](docs/infrastructure/15-observability.md) | Logs, metrics, traces, alerts |
| 16 | [Testing Strategy](docs/infrastructure/16-testing-strategy.md) | Unit, integration, E2E, load tests |
| 17 | [Docker & Local Development](docs/infrastructure/17-docker-local-dev.md) | Docker Compose, local setup guide |
| 18 | [Production Deployment](docs/infrastructure/18-production-deployment.md) | Deployment topology, scaling path |
| 19 | [Scalability Strategy](docs/infrastructure/19-scalability-strategy.md) | 10K to 100K users growth plan |
| 20 | [Repository Structure](docs/20-repository-structure.md) | Full project layout |
| 21 | [Implementation Roadmap](docs/21-implementation-roadmap.md) | Milestones, deliverables, dependencies |
| 22 | [Architectural Decisions](docs/22-architectural-decisions.md) | ADRs with rationale and trade-offs |

---

## Quick Start (Local Development)

```bash
# Clone and enter the repo
git clone <repo>
cd sports-intelligence-platform

# Start all services
docker compose up -d

# Apply migrations
docker compose exec api python manage.py migrate

# Create superuser
docker compose exec api python manage.py createsuperuser

# Ingest sample fixture data
docker compose exec api python manage.py seed_fixtures --sport cricket
```

See [Docker & Local Development](docs/infrastructure/17-docker-local-dev.md) for full details.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Core API | Django 5.x + DRF |
| Real-Time Gateway | FastAPI + WebSockets |
| Event Backbone | Apache Kafka |
| Primary DB | PostgreSQL 16 |
| Cache / State | Redis 7 |
| Vector DB | pgvector (PostgreSQL extension) |
| AI Orchestration | LangGraph |
| LLM | OpenAI GPT-4o / Gemini (pluggable) |
| Task Queue | Celery + Redis broker |
| Embeddings | OpenAI text-embedding-3-small |
| Containerization | Docker + Docker Compose |
| Observability | Prometheus + Grafana + Loki |
