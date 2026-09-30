# 5. Redis Design

## 5.1 What Belongs in Redis vs PostgreSQL

| Data | Redis | PostgreSQL | Rationale |
|------|-------|------------|-----------|
| Current live score | ✅ Primary | ✅ Backup (match_scores) | Sub-millisecond read required |
| Current match status | ✅ Primary | ✅ Authoritative | Fast status check for WebSocket |
| Current odds | ✅ Primary | ✅ Authoritative (match_odds_current) | Fast reads for feed |
| Live match events (last 20) | ✅ Cache | ✅ Complete history | Feed recent events quickly |
| User personalized feed | ✅ Cache | ✅ Source | Rebuild on invalidation |
| Active WebSocket subscriptions | ✅ Only | ❌ | Ephemeral; lost on restart = reconnect |
| Rate limiting counters | ✅ Only | ❌ | Atomic increments, TTL-based |
| Session / JWT blacklist | ✅ Primary | ✅ Backup | Fast token check |
| Dedup event keys | ✅ (TTL 24h) | ✅ (unique constraints) | Both layers for safety |
| User preferences | ❌ | ✅ Primary | Not hot path; cached via feed |
| Match history | ❌ | ✅ Primary | Not latency-sensitive |
| AI conversation history | ❌ | ✅ Primary | Must be durable |

---

## 5.2 Redis Key Schema

All keys follow the pattern: `{namespace}:{entity}:{id}[:{sub_key}]`

### 5.2.1 Live Match State

```
# Current score (Hash)
match:score:{match_id}
  HSET fields:
    home_score      "145"
    away_score      "0"
    home_wickets    "3"
    away_wickets    "0"
    home_overs      "15.2"
    status          "live"
    sequence_number "892"
    updated_at      "1727781000"
  TTL: 24h from last update (extended on each update)
  TTL after completion: 6h

# Match metadata cache (Hash)
match:meta:{match_id}
  HSET fields:
    sport           "cricket"
    competition_id  "uuid"
    competition_name "IPL 2026"
    home_team_id    "uuid"
    home_team_name  "RCB"
    away_team_id    "uuid"
    away_team_name  "MI"
    scheduled_at    "2026-10-01T14:00:00Z"
    status          "live"
  TTL: 2h (refreshed on match.started, cleared after match.completed)

# Recent match events (Sorted Set, scored by event_sequence)
match:events:recent:{match_id}
  ZADD event_sequence serialized_event_json
  Keep only last 50 events: ZREMRANGEBYRANK 0 -(51)
  TTL: 24h
  Example stored value:
    {"type":"wicket","player":"Kohli","over":"16.3","description":"c Rohit b Bumrah"}

# Live match IDs (Set, for quick lookup of all live matches)
matches:live
  SADD match_id_1 match_id_2 ...
  No TTL (managed by match.started/match.completed events)

# Upcoming matches by sport (Sorted Set, scored by scheduled_at unix timestamp)
matches:upcoming:{sport_slug}
  ZADD scheduled_at_unix match_id
  TTL: 1h (rebuilt by scheduled job)
```

### 5.2.2 Odds State

```
# Current odds per match (Hash, one per market)
match:odds:{match_id}:{market_type}
  HSET fields:
    provider        "odds_provider_x"
    bookmaker       "Bet365"
    home_win        "1.85"
    away_win        "2.10"
    updated_at      "1727781000"
  TTL: 4h from last update

# Odds movement tracking (List, max 10 entries per market)
match:odds:history:{match_id}:{market_type}
  RPUSH {home_win}:{away_win}:{timestamp}
  LTRIM 0 9  (keep last 10 changes)
  TTL: 4h
```

### 5.2.3 User Feed Cache

```
# Personalized feed for a user (String, serialized JSON)
feed:{user_id}
  SET serialized_feed_json
  TTL: 5 minutes (short; invalidated on preference change or new match)
  
# User's followed match IDs (Set, for fast subscription check)
user:matches:{user_id}
  SADD match_id_1 match_id_2 ...
  TTL: 10 minutes (rebuilt from preferences)
```

### 5.2.4 WebSocket Subscriptions

```
# Active WebSocket connections per match (Set of connection_ids)
ws:match:subs:{match_id}
  SADD connection_id_1 connection_id_2 ...
  TTL: none (connections self-remove on disconnect)
  Used by: fan-out logic to know who to notify

# Connection to user mapping (Hash)
ws:conn:{connection_id}
  HSET fields:
    user_id     "uuid"
    match_id    "uuid"
    gateway_id  "gateway-pod-1"  # which gateway instance holds the connection
    connected_at "1727781000"
  TTL: 2h (extended on activity; removed on disconnect)

# Match subscription count (String, atomic counter)
ws:match:count:{match_id}
  INCR / DECR
  TTL: none
```

### 5.2.5 Rate Limiting

```
# API rate limit (sliding window per user per endpoint)
rl:api:{user_id}:{endpoint_key}
  INCR with TTL 60s
  Check: if value > limit → 429

# AI rate limit (per user per hour)
rl:ai:{user_id}
  INCR with TTL 3600s
  Limit: 20 requests/hour

# Ingestion rate limit (per provider)
rl:provider:{provider_name}
  INCR with TTL 1s
  Limit: configured per provider SLA
```

### 5.2.6 Deduplication

```
# Event dedup (prevent reprocessing same Kafka event)
dedup:event:{event_id}
  SET "1" EX 86400  (24h TTL)
  Check with SETNX: if returns 0, already processed, skip
```

### 5.2.7 Token / Auth

```
# JWT access token blacklist (revoked tokens, e.g., on logout)
auth:blacklist:{jti}
  SET "1" EX {remaining_ttl}
  
# Password reset tokens
auth:reset:{token_hash}
  SET user_id EX 3600  (1h TTL)
```

---

## 5.3 Redis Data Structure Selection Rationale

| Use Case | Structure | Reason |
|---|---|---|
| Match score | Hash | Multiple fields, atomic partial updates with HMSET |
| Recent events | Sorted Set | Natural ordering by sequence_number; range queries |
| Live match IDs | Set | O(1) membership check, SADD/SREM on state change |
| WebSocket subscribers | Set per match | Fan-out: iterate members; SADD/SREM on connect/disconnect |
| Odds history | List | Time-ordered, LPOP/RPUSH, LTRIM to cap size |
| Rate limiting | String + INCR | Atomic increment, TTL-based window |
| Feed cache | String | Simple GET/SET/DEL for cache invalidation |
| Event dedup | String (SETNX) | Atomic check-and-set, automatic expiry |

---

## 5.4 Redis Configuration Recommendations

```
# Redis configuration for production
maxmemory 4gb
maxmemory-policy allkeys-lru  # Evict LRU keys when memory full
                               # Feed cache and match state are safe to evict (rebuilt on miss)

save ""                        # Disable RDB snapshots for pure cache Redis
appendonly no                  # No AOF for cache (prefer AOF=yes for auth/dedup Redis)

# Recommended: Two Redis instances
# redis-cache: LRU eviction, no persistence (feed, match state, odds)
# redis-auth:  AOF persistence (auth blacklist, dedup keys, rate limits)
```

---

## 5.5 Redis Pub/Sub for WebSocket Fan-out

The WebSocket gateway subscribes to Redis Pub/Sub channels to receive events from processors:

```
# Channels
channel: ws:match:{match_id}     # Score updates, match events for a match
channel: ws:user:{user_id}       # Personal notifications, feed updates

# Processor publishes:
PUBLISH ws:match:{match_id} serialized_event_json

# WebSocket gateway subscribes on connection:
SUBSCRIBE ws:match:{match_id}
# On disconnect:
UNSUBSCRIBE ws:match:{match_id}
```

**Note:** Redis Pub/Sub is fire-and-forget. For delivery guarantees to currently connected clients, the gateway reads from the pub/sub channel and delivers over WebSocket. If a client is disconnected, they reconnect and fetch missed events via REST API `GET /api/matches/{id}/events?since={timestamp}`.
