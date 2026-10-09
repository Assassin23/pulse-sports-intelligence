# Milestone 6: WebSocket Live Updates — Execution Plan

## 1. Overview & Objectives

**Goal:** Deliver real-time, low-latency live score updates and match events directly to client applications without HTTP polling.

- **Target Latency:** Provider/Kafka event → Client UI render in `< 3 seconds`.
- **Target Concurrency:** Support thousands of concurrent open WebSocket connections per instance.
- **Protocol:** WebSocket (`ws://` / `wss://`) streaming JSON frames.
- **Service Name:** `ws_gateway` (Dedicated FastAPI microservice).

---

## 2. Architecture & Service Rationale

### Why a Separate FastAPI Service?

1. **Async Concurrency vs. Synchronous Workloads:**
   - **Django** handles relational business logic, ORM transactions, admin, migrations, and standard REST endpoints on port `8000`.
   - **FastAPI + Uvicorn (`asyncio`)** on port `8001` handles long-lived, idle-heavy, I/O-bound persistent WebSocket connections.
2. **Stateless Fan-Out:**
   - The WebSocket gateway is completely stateless. It does not query PostgreSQL directly.
   - It reads initial state from Redis caches (`match:score:{id}`, `match:events:recent:{id}`) and subscribes to Redis Pub/Sub channels for streaming updates.
3. **Independent Scalability:**
   - During major live matches (e.g., Champions League final, World Cup), WebSocket connections can scale horizontally behind a load balancer without adding connection overhead to Django application workers.

---

## 3. High-Level System Architecture

```text
       ┌────────────────────────┐
       │ Ingestion Worker       │
       └───────────┬────────────┘
                   │ Kafka (sports.score.updated, sports.match.event)
                   ▼
       ┌────────────────────────┐
       │ Django Kafka Consumers │
       └───────────┬────────────┘
                   │ 1. Writes to PostgreSQL & updates Redis state
                   │ 2. PUBLISH to Redis channel: ws:match:{match_id}
                   ▼
           ╔═════════════════╗
           ║ Redis Pub/Sub   ║
           ╚═══════╤═════════╝
                   │ Subscribes to channels
                   ▼
       ┌────────────────────────┐
       │ FastAPI pulse-ws-gateway│ (Port 8001, Root Directory)
       │ - Initial snapshot     │
       │ - Real-time fan-out    │
       │ - JWT auth             │
       └───────────┬────────────┘
                   │ WebSocket Frames
                   ▼
       ┌────────────────────────┐
       │ Frontend (pulse-FE)    │
       │ React useMatchWebSocket│
       └────────────────────────┘
```

### Workspace Directory Layout

```text
d:/WorkSpace/myne/Pulse/
├── pulse-FE/                     # Frontend client (Vite, React 19, TanStack Router)
├── sports-intelligence-platform/ # Backend API (Django 5, DRF, Celery, Kafka)
└── pulse-ws-gateway/             # WebSocket Gateway (Standalone FastAPI Microservice)
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                   # FastAPI app, routes & WebSocket endpoints
    ├── auth.py                   # JWT verification
    ├── redis_client.py           # Async Redis client pool (redis.asyncio)
    ├── config.py                 # Service configuration
    └── schemas.py                # JSON WebSocket payloads & types
```

---

## 4. Detailed Component Implementation

### Component 1: `pulse-ws-gateway` Service (FastAPI)

Directory: `d:/WorkSpace/myne/Pulse/pulse-ws-gateway/`

```text
pulse-ws-gateway/
├── Dockerfile
├── requirements.txt
├── __init__.py
├── main.py              # FastAPI app, CORS, routes & lifecycle
├── auth.py              # JWT token verification (shared secret/key)
├── redis_client.py      # Async Redis client pool (redis.asyncio)
├── config.py            # Pydantic BaseSettings for gateway env vars
├── schemas.py           # Message response schemas & typing
└── health.py            # /health & readiness endpoints
```

#### Endpoints:
1. **`GET /health`**: Healthcheck endpoint for Docker/K8s readiness probes.
2. **`WS /ws/match/{match_id}`**:
   - Query Parameters: `?token=<jwt>` (optional for guests if configured, required for authenticated actions), `?since=<sequence_number>` (for reconnection).
   - **Step 1:** On connect, verify token via `auth.py`.
   - **Step 2:** Fetch snapshot from Redis:
     - Score from `match:score:{match_id}`
     - Recent events from `match:events:recent:{match_id}`
     - Emit `{ "type": "initial_state", "score": ..., "events": [...] }`
   - **Step 3:** Subscribe to Redis Pub/Sub channel `ws:match:{match_id}` and stream incoming messages.
   - **Step 4:** On disconnect, cleanly unsubscribe and remove connection tracking.
3. **`WS /ws/feed`**:
   - Personal notification channel subscribing to `ws:user:{user_id}` for personalized goal alerts.

---

### Component 2: Redis Pub/Sub Publishing from Django

Ensure existing consumers in `sports-intelligence-platform` publish updates immediately after persisting them:

1. **Score Updates (`ScoreProcessorConsumer` in `sports_platform/matches/`):**
   - Redis Channel: `ws:match:{match_id}`
   - Published Message:
     ```json
     {
       "type": "score_updated",
       "match_id": "uuid",
       "sport": "football",
       "score": {
         "home": 2,
         "away": 1,
         "minute": "67'",
         "status": "live"
       },
       "sequence_number": 42,
       "timestamp": "2026-10-08T13:45:00Z"
     }
     ```
2. **Match Events (`EventProcessorConsumer` in `sports_platform/matches/`):**
   - Redis Channel: `ws:match:{match_id}`
   - Published Message:
     ```json
     {
       "type": "match_event",
       "match_id": "uuid",
       "event": {
         "id": "uuid",
         "type": "goal",
         "minute": 67,
         "team_name": "Arsenal",
         "player_name": "Bukayo Saka",
         "description": "GOAL · Arsenal — Bukayo Saka"
       },
       "sequence_number": 43,
       "timestamp": "2026-10-08T13:45:10Z"
     }
     ```

---

### Component 3: Docker & Infrastructure

1. **Dockerfile (`pulse-ws-gateway/Dockerfile`):**
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8001
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
   ```

2. **Add to `sports-intelligence-platform/docker-compose.yml`:**
   ```yaml
   ws-gateway:
     build:
       context: ../pulse-ws-gateway
       dockerfile: Dockerfile
     command: uvicorn main:app --host 0.0.0.0 --port 8001 --reload
     ports:
       - "8001:8001"
     environment:
       REDIS_URL: redis://redis:6379/0
       JWT_SIGNING_KEY: local-dev-jwt-signing-key-change-in-production
     volumes:
       - ../pulse-ws-gateway:/app
     depends_on:
       redis:
         condition: service_healthy
   ```

---

### Component 4: Frontend Live Integration (`pulse-FE`)

1. **React Custom Hook (`src/lib/use-match-socket.ts`):**
   - Connects to `ws://localhost:8001/ws/match/{matchId}`.
   - Reconnection logic: Exponential backoff (1s, 2s, 4s, 8s, up to 30s max).
   - Handles message dispatch:
     - `initial_state`: Sets current score and timeline.
     - `score_updated`: Updates score counters with pulse animation.
     - `match_event`: Prepends new event to timeline and triggers toast notification.
2. **Dashboard Integration (`pulse-dashboard.tsx`):**
   - Active match uses WebSocket stream when available.
   - Falls back gracefully to HTTP polling (every 15s) if the socket drops.

---

## 5. Execution Phases

| Phase | Tasks | Key Deliverables |
| :--- | :--- | :--- |
| **Phase 1: Gateway Core** | Create `ws_gateway` package, JWT auth helper, and async Redis client. | `ws_gateway/main.py`, `auth.py`, `redis_client.py` |
| **Phase 2: Redis Pub/Sub Bridge** | Add `redis.publish(...)` calls to Kafka consumers & match simulator. | Pub/Sub triggers on live score/event updates |
| **Phase 3: Dockerization** | Build `Dockerfile` and configure port `8001` in `docker-compose.yml`. | Running `ws-gateway` container with passing `/health` check |
| **Phase 4: Frontend Hook** | Create `useMatchWebSocket` hook in `pulse-FE` and wire into `pulse-dashboard.tsx`. | Real-time score updates in browser without page refresh |
| **Phase 5: Verification** | Run event simulator / management command and observe instant UI update. | Latency verification (`< 100ms` over local WebSocket) |

---

## 6. Verification & Test Plan

1. **Health Check:**
   `curl http://localhost:8001/health` → `{"status": "healthy"}`
2. **WebSocket Connection Test:**
   Using a WebSocket client (e.g., Postman or browser `wscat`):
   ```bash
   wscat -c "ws://localhost:8001/ws/match/<match_id>"
   ```
   Verify receipt of `initial_state` JSON message.
3. **Pub/Sub Test:**
   Publish a test score into Redis:
   ```bash
   redis-cli PUBLISH ws:match:<match_id> '{"type":"score_updated","score":{"home":3,"away":1}}'
   ```
   Verify the message arrives instantly in the connected client.
4. **End-to-End Simulation:**
   Run simulated match events and verify the Pulse frontend updates scores and timeline dynamically in real time.
