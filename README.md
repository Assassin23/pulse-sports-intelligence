# ⚡ Pulse — Sports Intelligence Platform

> **Production-grade personalized real-time sports intelligence platform.**  
> Built with Django 5, DRF, PostgreSQL, Redis, Apache Kafka, FastAPI WebSockets, and LangGraph.

[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/Django-5.0+-green.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 📖 Overview

Pulse is a real-time sports intelligence platform that delivers personalized live scores, deep game analytics, AI-powered contextual query answers, and notifications.

### 🌟 Key Features
- **Personalized Sports Preferences:** Users select up to 3 sports (e.g., Cricket, Football, Tennis) and follow specific teams, competitions, countries, and players.
- **High-Throughput Real-Time Ingestion:** Event-driven architecture with Apache Kafka for zero-lag score ingestion and updates.
- **Fast Live Match State:** Redis-backed state machine for sub-second live score queries and caching.
- **AI Contextual Copilot & RAG:** LangGraph workflow combining live match statistics, historical head-to-head records, and news retrieval for intelligent sports Q&A.
- **Live Updates via WebSockets:** Real-time client updates over WebSockets powered by FastAPI.
- **Enterprise Security & Reliability:** JWT authentication with token revocation, rate limiting, and request ID distributed tracing.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Core API** | Django 5.x + Django REST Framework | Domain logic, user auth, preferences, CRUD APIs |
| **Real-Time Gateway** | FastAPI + WebSockets | High-concurrency live match event streaming |
| **Event Backbone** | Apache Kafka | Event streaming (match discovery, score updates, events) |
| **Primary Database** | PostgreSQL 16 + pgvector | Relational system of record and vector embeddings |
| **Cache & Real-Time State** | Redis 7 | Live score state, user feeds, rate-limiting, and blacklists |
| **Task Queue & Scheduler** | Celery + Redis broker | Background ingestion and async tasks |
| **AI Orchestration & LLM** | LangGraph + OpenAI / Gemini | Multi-agent reasoning for sports intelligence queries |
| **Observability** | Prometheus, Grafana, Loki | Metrics, dashboarding, and structured logging |

---

## 📂 System Design & Documentation Index

Comprehensive documentation is available under [`docs/`](docs/):

| # | Document | Description |
|---|---|---|
| 01 | [Overview & Requirements](docs/01-overview-and-requirements.md) | Executive summary, functional & non-functional requirements |
| 02 | [High-Level Architecture](docs/architecture/02-high-level-architecture.md) | System topology, service boundaries, and module design |
| 03 | [Event-Driven Architecture](docs/architecture/03-event-driven-architecture.md) | Kafka topic topology, event contracts, partitioning & DLQs |
| 04 | [Database Design](docs/data-model/04-database-design.md) | PostgreSQL schema, indexing strategy, and relationships |
| 05 | [Redis Design](docs/data-model/05-redis-design.md) | Key schema, eviction policies, TTLs, and live state store |
| 06 | [External Provider Architecture](docs/architecture/06-provider-architecture.md) | Provider abstraction, adapter contracts, and circuit breakers |
| 07 | [Real-Time Architecture](docs/architecture/07-realtime-architecture.md) | WebSocket gateway, connection registry, and pub/sub |
| 08 | [Odds Architecture](docs/architecture/08-odds-architecture.md) | Betting odds ingestion, normalization, and movement tracking |
| 09 | [AI & RAG Architecture](docs/ai/09-ai-rag-architecture.md) | Document pipeline, vector search, and reranking |
| 10 | [LangGraph Workflow](docs/ai/10-langgraph-workflow.md) | Agent graph, tool invocation, and decision paths |
| 11 | [REST API Design](docs/api/11-api-design.md) | Endpoint specifications, payloads, and response envelopes |
| 12 | [Authentication & Security](docs/api/12-auth-and-security.md) | JWT auth, token blacklisting, RBAC, and rate limits |
| 13 | [Notifications](docs/architecture/13-notifications.md) | Fan-out rules, push notifications, and live alerts |
| 14 | [Reliability & Resilience](docs/infrastructure/14-reliability.md) | Retries, backoff, circuit breakers, and fallback mechanisms |
| 15 | [Observability](docs/infrastructure/15-observability.md) | Tracing, metric collection, and Loki logging |
| 16 | [Testing Strategy](docs/infrastructure/16-testing-strategy.md) | Unit, integration, Kafka testcontainers, and load tests |
| 17 | [Docker & Local Dev](docs/infrastructure/17-docker-local-dev.md) | Container setup and local runbook |
| 18 | [Production Deployment](docs/infrastructure/18-production-deployment.md) | Cloud deployment architecture and scaling |
| 19 | [Scalability Strategy](docs/infrastructure/19-scalability-strategy.md) | Scaling from 10k to 100k+ concurrent users |
| 20 | [Repository Structure](docs/20-repository-structure.md) | Code organization and modular monolith boundaries |
| 21 | [Implementation Roadmap](docs/21-implementation-roadmap.md) | Detailed milestone breakdown and deliverables |
| 22 | [Architectural Decisions (ADRs)](docs/22-architectural-decisions.md) | Key architectural decision records and trade-offs |

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose
- [Python 3.12+](https://www.python.org/) (optional for local non-container runs)

### 2. Clone & Configure
```bash
git clone https://github.com/Assassin23/pulse-sports-intelligence.git
cd pulse-sports-intelligence

# Copy environment variables
cp .env.example .env
```

### 3. Run with Docker Compose
```bash
docker compose up -d
```

### 4. Database Migrations & Initial Seed
```bash
# Run migrations
docker compose exec api python manage.py migrate

# Seed catalog (sports, countries, competitions, teams, players)
docker compose exec api python manage.py seed_sports

# Create admin superuser
docker compose exec api python manage.py createsuperuser
```

### 5. Verify Running Services
- **API Health Check**: `http://localhost:8000/health/`
- **REST API Root**: `http://localhost:8000/api/v1/`
- **Django Admin**: `http://localhost:8000/admin/`

---

## 🧪 Running Tests

```bash
# Run all unit and API tests with pytest
pytest tests/
```

---

## 🗺️ Roadmap Milestones

- [x] **Milestone 1: Foundation — Auth + User Preferences** (Complete)
- [ ] **Milestone 2: Sports Reference Data + Provider Integration**
- [ ] **Milestone 3: Kafka + Match Discovery Pipeline**
- [ ] **Milestone 4: Live Match Processing + Redis State Engine**
- [ ] **Milestone 5: Personalized User Feed**
- [ ] **Milestone 6: WebSocket Gateway & Live Client Streaming**
- [ ] **Milestone 7: Betting Odds Ingestion & Tracking**
- [ ] **Milestone 8: AI Context Copilot & RAG Pipeline**
- [ ] **Milestone 9: Notifications & Real-Time Alerts**
- [ ] **Milestone 10: Production Hardening & Observability**

---

## 📄 License
This project is licensed under the MIT License.
