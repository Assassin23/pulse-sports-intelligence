# 1. Overview & Requirements

## 1.1 Executive Summary

The Sports Intelligence Platform is a personalized, real-time sports data and AI assistant platform. Users select up to 3 sports and follow countries, clubs, competitions, and players. The system delivers a curated live feed, real-time scores, match events, odds tracking, and AI-powered match analysis.

The architecture separates concerns cleanly:

- **Ingestion layer** polls external sports data providers on a fixed schedule, isolated from user traffic.
- **Kafka** acts as the event backbone decoupling ingestion from processing.
- **Processing consumers** normalize events, update Redis (live state), and persist to PostgreSQL (durable history).
- **Django API** serves user-facing REST endpoints backed by Redis for hot reads.
- **FastAPI WebSocket gateway** fans out real-time events to connected clients.
- **LangGraph AI assistant** answers match questions using deterministic backend tools for live data and RAG for contextual knowledge.

The initial system is designed for a single senior engineer to build and deploy. It starts as a **Django modular monolith** with separate lightweight services only where there is a genuine architectural reason (WebSocket gateway, ingestion workers).

---

## 1.2 Functional Requirements

### User Preferences
- FR-01: Users can register and authenticate.
- FR-02: Users can select up to 3 sports.
- FR-03: For each sport, users can follow: countries, clubs/teams, competitions/leagues, and optionally individual players.
- FR-04: Preference changes take effect immediately (preference update event published to Kafka).

### Personalized Feed
- FR-05: Users receive a personalized feed of upcoming matches based on their preferences.
- FR-06: The feed updates in real-time for live matches.
- FR-07: The feed includes match status, current score, key events, and odds.

### Live Match Data
- FR-08: Live scores update in real-time via WebSocket.
- FR-09: Match events (goals, wickets, red cards, etc.) are streamed in real-time.
- FR-10: Match statistics are available on demand.

### Odds
- FR-11: Current odds are displayed for live and upcoming matches.
- FR-12: Odds changes are tracked over time (for informational purposes only).
- FR-13: Odds are sourced from external providers and treated as informational data.

### Notifications
- FR-14: Users receive notifications for: match start, goals, wickets, red cards, major events, match end.
- FR-15: Notifications are delivered via WebSocket (real-time) and push (mobile/PWA).
- FR-16: Users can configure notification preferences per sport and event type.

### AI Match Assistant
- FR-17: Users can ask natural language questions about any match.
- FR-18: The assistant uses deterministic tools for live/current data (scores, events, stats).
- FR-19: The assistant uses RAG for contextual knowledge (team history, rules, player profiles).
- FR-20: Conversation history is persisted per user per match.
- FR-21: The assistant cites its data sources.

---

## 1.3 Non-Functional Requirements

### Performance
- NFR-01: Live score update latency < 3 seconds end-to-end (provider to client).
- NFR-02: REST API p99 latency < 200ms for cached endpoints.
- NFR-03: WebSocket connection establishment < 500ms.
- NFR-04: AI assistant first-token latency < 3 seconds.

### Scalability
- NFR-05: Initial target: 10K users, 1K concurrent users, 100 live matches.
- NFR-06: Growth target: 100K users, 10K concurrent users, 1K+ live matches.
- NFR-07: The system must scale horizontally without re-architecture.

### Reliability
- NFR-08: System availability: 99.9% uptime.
- NFR-09: External provider failures must not degrade the user experience beyond stale data.
- NFR-10: No data loss for match events (Kafka retention minimum 7 days).
- NFR-11: Kafka consumers must be idempotent.
- NFR-12: Duplicate and out-of-order events must be handled gracefully.

### Security
- NFR-13: All API endpoints authenticated via JWT.
- NFR-14: Sensitive data encrypted at rest and in transit.
- NFR-15: AI prompts hardened against injection attacks.
- NFR-16: Rate limiting enforced at API and AI layers.

### Maintainability
- NFR-17: Clear service/module boundaries.
- NFR-18: > 80% test coverage on business logic.
- NFR-19: Comprehensive observability from day one.
- NFR-20: A single engineer can understand and operate the entire system.

### Compliance
- NFR-21: Odds data is informational only. No gambling or betting functionality.
- NFR-22: GDPR-compliant user data handling.
- NFR-23: AI conversations are stored per-user and accessible only to that user.
