# 7. Real-Time Architecture

## 7.1 End-to-End Flow

```
Provider API (polling)
    │  every 15-30s per live match
    ▼
Ingestion Worker
    │  normalizes to ProviderScore / ProviderMatchEvent
    │  publishes to Kafka
    ▼
Kafka (sports.score.updated / sports.match.event)
    │  partitioned by match_id
    ▼
Score Processor / Event Processor (Django consumer)
    │  1. Idempotency check (dedup key in Redis)
    │  2. Optimistic concurrency check (sequence_number)
    │  3. Write to PostgreSQL (match_scores / match_events)
    │  4. Update Redis (match:score:{id}, match:events:recent:{id})
    │  5. PUBLISH to Redis channel ws:match:{match_id}
    ▼
FastAPI WebSocket Gateway
    │  Subscribed to ws:match:{match_id} via Redis Pub/Sub
    │  Fan-out to all connected WebSocket clients for that match
    ▼
Client (Browser / Mobile App)
```

**End-to-end latency target:** Provider update → client display < 3 seconds.

---

## 7.2 WebSocket Gateway (FastAPI)

The WebSocket gateway is a **stateless FastAPI service**. It does NOT hold state — all subscription state is in Redis.

```python
# ws_gateway/main.py

import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from ws_gateway.auth import verify_ws_token
from ws_gateway.redis_client import get_redis
import redis.asyncio as aioredis

app = FastAPI()
logger = logging.getLogger(__name__)


@app.websocket("/ws/match/{match_id}")
async def match_websocket(
    websocket: WebSocket,
    match_id: str,
    token: str,  # passed as query param: ?token=...
):
    # 1. Authenticate
    user_id = await verify_ws_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    conn_id = f"{user_id}:{match_id}:{id(websocket)}"

    redis: aioredis.Redis = await get_redis()

    try:
        # 2. Register subscription in Redis
        await redis.sadd(f"ws:match:subs:{match_id}", conn_id)
        await redis.hset(f"ws:conn:{conn_id}", mapping={
            "user_id": user_id,
            "match_id": match_id,
        })
        await redis.incr(f"ws:match:count:{match_id}")

        # 3. Send initial state (last-known-good from Redis)
        current_score = await redis.hgetall(f"match:score:{match_id}")
        recent_events = await redis.zrange(
            f"match:events:recent:{match_id}", 0, -1
        )
        await websocket.send_json({
            "type": "initial_state",
            "score": current_score,
            "recent_events": [json.loads(e) for e in recent_events],
        })

        # 4. Subscribe to Redis Pub/Sub and fan out
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"ws:match:{match_id}")

        async def listen():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])

        await listen()

    except WebSocketDisconnect:
        logger.info("Client disconnected", extra={"conn_id": conn_id})
    finally:
        # 5. Clean up subscriptions
        await redis.srem(f"ws:match:subs:{match_id}", conn_id)
        await redis.delete(f"ws:conn:{conn_id}")
        await redis.decr(f"ws:match:count:{match_id}")
        await pubsub.unsubscribe(f"ws:match:{match_id}")
        await pubsub.close()


@app.websocket("/ws/feed")
async def feed_websocket(websocket: WebSocket, token: str):
    """Personal feed WebSocket for notifications and feed updates."""
    user_id = await verify_ws_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    redis: aioredis.Redis = await get_redis()

    pubsub = redis.pubsub()
    await pubsub.subscribe(f"ws:user:{user_id}")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"ws:user:{user_id}")
        await pubsub.close()
```

---

## 7.3 WebSocket Message Schema

All messages sent over WebSocket are JSON with a `type` discriminator:

```json
// Score update
{
  "type": "score_updated",
  "match_id": "uuid",
  "sport": "cricket",
  "score": {
    "home": {"team_id": "uuid", "runs": 145, "wickets": 3, "overs": "15.2"},
    "away": {"team_id": "uuid", "runs": 0, "wickets": 0, "overs": "0.0"}
  },
  "sequence_number": 892,
  "timestamp": "2026-10-01T15:30:00Z"
}

// Match event
{
  "type": "match_event",
  "match_id": "uuid",
  "event": {
    "type": "wicket",
    "sequence": 45,
    "over": "16.3",
    "player": "Virat Kohli",
    "description": "c Rohit b Bumrah 0 (1b)",
    "score_after": {"runs": 145, "wickets": 4}
  },
  "timestamp": "2026-10-01T15:32:10Z"
}

// Match status change
{
  "type": "match_status_changed",
  "match_id": "uuid",
  "old_status": "live",
  "new_status": "completed",
  "result": "RCB won by 23 runs",
  "timestamp": "2026-10-01T17:45:00Z"
}

// Personal notification (on /ws/feed channel)
{
  "type": "notification",
  "notification_type": "goal",
  "match_id": "uuid",
  "title": "GOAL! ⚽",
  "body": "Chelsea 2-1 Barcelona. Erling Haaland scores in 67'",
  "timestamp": "2026-10-01T15:32:10Z"
}
```

---

## 7.4 Reconnection Strategy

**Client-side reconnection (recommended implementation):**

```javascript
// Client reconnection with exponential backoff
class MatchWebSocket {
  constructor(matchId, token) {
    this.matchId = matchId;
    this.token = token;
    this.retryDelay = 1000;  // start at 1s
    this.maxDelay = 30000;   // cap at 30s
    this.lastEventTimestamp = null;
  }

  connect() {
    const url = `wss://api.example.com/ws/match/${this.matchId}?token=${this.token}`;
    this.ws = new WebSocket(url);
    
    this.ws.onopen = () => {
      this.retryDelay = 1000;  // reset on success
      // If reconnecting, fetch missed events since last known timestamp
      if (this.lastEventTimestamp) {
        this.fetchMissedEvents();
      }
    };

    this.ws.onclose = (event) => {
      if (event.code !== 1000) {  // not a clean close
        setTimeout(() => this.connect(), this.retryDelay);
        this.retryDelay = Math.min(this.retryDelay * 2, this.maxDelay);
      }
    };
  }

  fetchMissedEvents() {
    // REST API fallback for missed events during disconnect
    fetch(`/api/matches/${this.matchId}/events?since=${this.lastEventTimestamp}`)
      .then(r => r.json())
      .then(events => events.forEach(e => this.handleEvent(e)));
  }
}
```

**Server-side:** WebSocket connections are short-lived from the server's perspective. If the gateway restarts, clients reconnect automatically. Redis pub/sub subscriptions are re-established on reconnect.

---

## 7.5 Fan-out Architecture

```
Processor publishes to Redis Pub/Sub channel: ws:match:{match_id}
    │
    ├── Gateway Instance 1 (subscribed) → fans out to 50 connected clients
    ├── Gateway Instance 2 (subscribed) → fans out to 60 connected clients  
    └── Gateway Instance 3 (subscribed) → fans out to 40 connected clients

Total fan-out: 150 clients receive the update simultaneously
```

Each gateway instance subscribes to **all active match channels**. This is efficient because Redis Pub/Sub is lightweight (no message persistence). The gateway uses **asyncio** to handle thousands of concurrent connections.

**Scaling:** At 10K concurrent users with 100 matches, assuming average 10 users/match = manageable. At 10K concurrent across 1K matches, use multiple gateway instances behind a load balancer (any instance can handle any connection because state is in Redis).

---

## 7.6 Provider Outage Handling

```
Provider goes down
    │
    ├── Ingestion worker fails to fetch → logs error, increments metric
    ├── Circuit breaker opens after 5 consecutive failures
    ├── No new Kafka events for that match
    ├── Redis score state becomes stale (no new updates)
    ├── WebSocket clients see no updates (silent degradation)
    │
    └── Client-side: display "Last updated X minutes ago" badge
        Server-side: expose match:score:{match_id} updated_at field
        API response: include data_freshness_seconds in match response

Recovery:
    ├── Circuit breaker half-opens after 5 minutes
    ├── Test request to provider
    ├── If successful: resume polling, close circuit breaker
    ├── Backfill: fetch latest score snapshot from provider
    └── Publish reconciliation event to Kafka to update Redis + PostgreSQL
```

---

## 7.7 Event Ordering Guarantee

```
Problem: Two score updates arrive out of order:
  sequence_number=892 arrives first → Redis updated to seq=892
  sequence_number=891 arrives second → MUST NOT overwrite seq=892

Solution: Lua script for atomic check-and-set in Redis:
```

```lua
-- Redis Lua script: update score only if sequence is newer
local current_seq = tonumber(redis.call('HGET', KEYS[1], 'sequence_number') or 0)
local new_seq = tonumber(ARGV[1])

if new_seq > current_seq then
    redis.call('HMSET', KEYS[1], unpack(ARGV, 2))
    return 1  -- updated
else
    return 0  -- skipped (out of order)
end
```

```python
# Called from Score Processor
def update_score_atomic(redis_client, match_id, score_data, sequence_number):
    key = f"match:score:{match_id}"
    args = [str(sequence_number)] + [
        item for pair in score_data.items() for item in pair
    ]
    result = redis_client.eval(UPDATE_SCORE_LUA, 1, key, *args)
    return result == 1  # True if updated, False if skipped
```
