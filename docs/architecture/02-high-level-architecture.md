# 2. High-Level Architecture

## 2.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL DATA PROVIDERS                                │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│   │  Provider A  │  │  Provider B  │  │  Provider C  │  │  Odds API    │      │
│   │ (fixtures,   │  │ (live score, │  │  (stats,     │  │ (bookmaker   │      │
│   │  events)     │  │  events)     │  │   history)   │  │  feeds)      │      │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
└──────────┼─────────────────┼─────────────────┼─────────────────┼───────────────┘
           │                 │                 │                 │
           ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          INGESTION LAYER (Separate Services)                    │
│   ┌─────────────────────────┐              ┌──────────────────────────┐        │
│   │   Sports Ingestion       │              │   Odds Ingestion Worker  │        │
│   │   Workers (one per       │              │   (polls odds providers, │        │
│   │   provider, Celery Beat) │              │    separate cadence)     │        │
│   └────────────┬────────────┘              └──────────────┬───────────┘        │
└────────────────┼──────────────────────────────────────────┼────────────────────┘
                 │                                          │
                 ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          APACHE KAFKA (Event Backbone)                          │
│                                                                                 │
│  sports.match.discovered  │  sports.score.updated  │  sports.odds.updated      │
│  sports.match.started     │  sports.match.event    │  sports.match.completed   │
│  sports.user.pref.updated │  notifications.requested                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     PROCESSING LAYER (Django Kafka Consumers)                   │
│                                                                                 │
│  ┌───────────────────┐  ┌───────────────────┐  ┌────────────────────────────┐ │
│  │  Match Processor  │  │  Score Processor  │  │  Odds Processor            │ │
│  │  (normalizes,     │  │  (updates Redis,  │  │  (normalizes, persists,    │ │
│  │   persists match) │  │   persists event) │  │   updates Redis state)     │ │
│  └───────────────────┘  └───────────────────┘  └────────────────────────────┘ │
│                                                                                 │
│  ┌───────────────────┐  ┌────────────────────────────────────────────────────┐ │
│  │  Event Processor  │  │  Notification Processor                            │ │
│  │  (match events,   │  │  (evaluates rules, publishes notifications)        │ │
│  │   fan-out ready)  │  └────────────────────────────────────────────────────┘ │
│  └───────────────────┘                                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                 │
          ┌──────┴──────┐
          ▼             ▼
┌──────────────┐  ┌──────────────────────────────┐
│  PostgreSQL  │  │            Redis              │
│  (durable    │  │  (live state, feed cache,    │
│   history)   │  │   subscriptions, rate limits) │
└──────┬───────┘  └──────────────┬───────────────┘
       │                         │
       ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          API LAYER                                              │
│                                                                                 │
│  ┌────────────────────────────────────┐  ┌──────────────────────────────────┐  │
│  │    Django + DRF (Core API)         │  │  FastAPI (WebSocket Gateway)     │  │
│  │                                    │  │                                  │  │
│  │  /api/feed          /api/matches   │  │  ws://gateway/ws/match/{id}      │  │
│  │  /api/preferences   /api/odds      │  │  ws://gateway/ws/feed            │  │
│  │  /api/ai/ask        /api/users     │  │                                  │  │
│  └────────────────────────────────────┘  └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                 │                                │
                 ▼                                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                CLIENTS                                          │
│                Web Browser / Mobile App / PWA                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2.2 Service/Module Responsibilities

### Django Modular Monolith (Single Deployed Unit, Initial Phase)

The core application is a Django monolith organized as **Django apps** with clear internal boundaries. Each app owns its models, services, serializers, and views.

| App / Module | Responsibility |
|---|---|
| `users` | Registration, authentication, JWT issuance, user profiles |
| `preferences` | User sport/team/competition/player following logic |
| `feed` | Personalized feed assembly from Redis + PostgreSQL |
| `matches` | Match model, match detail, match events, match stats |
| `odds` | Odds model, current odds, odds history |
| `notifications` | Notification rules, user notification preferences, delivery |
| `ai` | LangGraph orchestration, conversation history, AI tools |
| `rag` | Document ingestion pipeline, embedding, retrieval |
| `kafka` | Kafka producer client, topic definitions, consumer registry |

### Separate Services (Justified by Architecture)

| Service | Why Separate |
|---|---|
| **Sports Ingestion Workers** | Polling external APIs on tight schedules; must scale independently; failure must not affect API |
| **Odds Ingestion Workers** | Different polling cadence (odds change faster); may have different SLA requirements |
| **FastAPI WebSocket Gateway** | WebSocket connections are long-lived; Django's WSGI/ASGI is not optimized for 1K+ persistent connections; FastAPI's async native model handles this better |
| **Celery Workers** | Async task execution for notifications, AI processing, RAG ingestion |

---

## 2.3 Data Flow Summary

### Ingestion Flow
```
Scheduler (Celery Beat)
  → Ingestion Worker calls Provider API
  → Raw response deserialized via Provider Adapter
  → Normalized to internal domain model
  → Published to Kafka topic
```

### Processing Flow
```
Kafka Consumer reads event
  → Idempotency check (dedup key in Redis/PostgreSQL)
  → Normalize/validate payload
  → Write to PostgreSQL (durable)
  → Update Redis (live state)
  → Publish downstream events (e.g., notifications.requested)
```

### Real-Time Delivery Flow
```
Redis pub/sub or Stream
  → WebSocket Gateway subscriber
  → Fan-out to connected clients subscribed to that match_id
```

### Read Flow (API)
```
Client → Django API → Redis (cache hit) → response
                    → Redis (cache miss) → PostgreSQL → Redis update → response
```
