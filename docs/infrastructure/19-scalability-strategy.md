# 19. Scalability Strategy

## 19.1 Current Scale: 10K Users / 1K Concurrent / 100 Live Matches

**Baseline capacity (what the initial architecture can handle without changes):**

| Component | Capacity | Headroom |
|---|---|---|
| Django API (2× t3.medium, 4 workers each) | ~800 req/s | Comfortable at 1K concurrent |
| FastAPI WS Gateway (2× t3.small) | ~2K concurrent connections | Comfortable |
| PostgreSQL (db.t3.medium + 1 read replica) | ~500 queries/s | Fine for 1K concurrent |
| Redis (cache.t3.medium) | ~100K ops/s | More than enough |
| Kafka (3 brokers) | ~50K messages/s | Well above peak |
| Celery Workers (1× t3.medium, 8 concurrency) | ~200 tasks/min | Sufficient |

---

## 19.2 Scaling Path: 100K Users / 10K Concurrent / 1K+ Live Matches

### Phase 1: Horizontal Scale (no re-architecture needed)

Scale before hitting limits:

```
API Servers:           2 → 6 instances (auto-scaling group)
WebSocket Gateways:    2 → 8 instances (sticky sessions via load balancer OR Redis-backed state)
Kafka Consumers:       1 → 4 instances per consumer group (auto-scale on lag)
Celery Workers:        1 → 4 VMs, 16 concurrent each
PostgreSQL:            Add 2 more read replicas (total: 3)
Redis:                 Upgrade to cache.r6g.large cluster mode (3 shards × 2 replicas)
```

### Phase 2: Kafka Partitions

```
Initial partition counts (at 100 live matches):
  sports.score.updated:  24 partitions (100 matches × 2 updates/min = manageable)
  sports.match.event:    24 partitions

At 1K live matches:
  sports.score.updated:  96 partitions   (1K × 2/min = 2K events/min)
  sports.match.event:    48 partitions
  
Rule: partitions should be 2-4× the number of consumer instances
  → 8 consumer instances → 32 partitions minimum
  
Partition count increase: add partitions during low-traffic window
  kafka-topics --alter --topic sports.score.updated --partitions 96
  (Note: increasing partitions affects ordering guarantees for existing messages)
```

### Phase 3: Database Scaling

```
PostgreSQL at 10K concurrent users:
  Problem: connection count explosion (10K users × persistent connections)
  Solution: PgBouncer connection pooler in front of PostgreSQL
  
  PgBouncer config:
    pool_mode = transaction   # Most efficient for Django
    max_client_conn = 10000   # Clients → PgBouncer
    default_pool_size = 100   # PgBouncer → PostgreSQL
    
  PostgreSQL connections stay at ~100-200 regardless of user count.

Read replicas:
  Route all read-heavy queries (feed, match history, standings) to read replicas
  Write queries (score updates, event inserts) stay on primary
  
  Django configuration:
    DATABASES = {
        "default": "primary",
        "read": "replica_1",
    }
    # Custom database router
```

### Phase 4: Redis Cluster Mode

```
Single Redis → Redis Cluster (3 shards):
  Shard 1: match:score:*, match:events:* (match state)
  Shard 2: feed:*, user:* (user data)
  Shard 3: rl:*, dedup:*, auth:* (rate limiting, dedup, auth)
  
  Note: Redis Cluster doesn't support PUBLISH across shards.
  WebSocket pub/sub: maintain separate Redis Sentinel for pub/sub only
  (pub/sub requires single Redis instance or use Redis Streams instead)
  
  Alternative at this scale: Redis Streams
    → Kafka-like consumption from Redis
    → Supports consumer groups with at-least-once delivery
    → Better than pub/sub for high fan-out
```

### Phase 5: WebSocket Scaling

```
10K concurrent WebSocket connections:

Problem: 8 gateway instances × 1.25K connections each = 10K connections
          Any instance can serve any connection (state in Redis)
          
Sticky sessions NOT required because:
  - All connection state is in Redis (ws:conn:{id}, ws:match:subs:{id})
  - Any gateway instance can fanout to any connection on the same Redis

Fan-out at scale:
  1K live matches × avg 10 subscribers = 10K connections
  Peak event (major goal): publish to 100 subscribers
  Each event: PUBLISH to Redis → 8 gateway instances each deliver to their ~10 subscribers
  
  Redis pub/sub scales to this comfortably.
  At 100K subscribers per match → use Redis Streams or Kafka consumer per match.
```

### Phase 6: Feed Performance

```
At 100K users: feed cache must be bulletproof.
  
Problem: 100K users all logging in after a big match → cache stampede
Solution: 
  1. Cache warming: pre-compute feeds for active users every 3 minutes
     (background Celery task, not on-demand)
  2. Short jitter on TTL: TTL = 5min + random(0-60s) to spread recomputation
  3. Probabilistic early expiration (PER):
     - When cache is 80% of TTL → 20% chance of recomputing
     - Prevents thundering herd at exactly TTL
  4. Circuit breaker on PostgreSQL feed query:
     - If PostgreSQL is slow → serve stale cached feed with freshness warning
```

### Phase 7: Ingestion Scaling

```
At 1K live matches:
  Polling frequency: 30s per match × 1K matches = 33 polls/s across all providers
  Provider limits: typically 100-500 requests/min
  
  Partitioned ingestion workers:
    Worker group 1: cricket matches (a-m competition_id)
    Worker group 2: cricket matches (n-z competition_id)
    Worker group 3: football matches
    ...
    
  Use provider's batch endpoints if available:
    "Give me all live match scores" → 1 API call instead of 1K
    
  WebSocket/Webhook providers:
    Some providers offer webhooks or WebSocket push
    → No polling needed; provider sends events
    → Eliminate ingestion workers entirely for webhook-capable providers
```

---

## 19.3 Scalability Metrics to Monitor

| Metric | Warning Threshold | Critical Threshold | Action |
|---|---|---|---|
| API p99 latency | > 500ms | > 2s | Add API instances |
| WebSocket connections / instance | > 5K | > 8K | Add gateway instances |
| Kafka consumer lag | > 1K messages | > 10K | Add consumers |
| PostgreSQL p99 query time | > 100ms | > 500ms | Add replica, optimize query, add index |
| Redis memory usage | > 70% | > 85% | Upgrade instance / add shard |
| Celery queue depth | > 500 tasks | > 2K tasks | Add workers |

---

## 19.4 Kubernetes (When to Move)

**Move to Kubernetes when:**
- Team size > 5 engineers.
- Need autoscaling based on match traffic spikes (e.g., World Cup day vs. off-season).
- Running 20+ pods across 5+ services.
- Need zero-downtime rolling deployments with health gates.

**Not needed for:**
- < 100K users.
- < 10 service instances.
- Team of 1-3 engineers.

The architecture is **Kubernetes-ready** from day one:
- Stateless API and WebSocket services.
- All state in Redis/PostgreSQL.
- Health check endpoints at `/health` and `/health/ready`.
- Configuration via environment variables.
- Docker images already built.
