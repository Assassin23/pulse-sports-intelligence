# 14. Reliability & Failure Handling

## 14.1 Failure Scenarios Matrix

| Component | Failure | Impact | Mitigation | Recovery |
|---|---|---|---|---|
| External Provider | API down | Stale data | Circuit breaker, fallback provider | Auto-resume on recovery |
| Kafka | Broker down | No new events | Kafka replication factor 3 | Auto-leader election |
| Redis | Instance down | Cache miss, WebSocket disruption | Redis Sentinel / Cluster | Rebuild from PostgreSQL |
| PostgreSQL | DB down | No reads/writes | Replica promotion | Failover to replica |
| Ingestion Worker | Crash | Missed polling cycles | Celery retry, Kubernetes restart | Auto-restart, catch-up on next cycle |
| Kafka Consumer | Crash | Message processing lag | Consumer group rebalance | Another instance takes over |
| WebSocket Gateway | Crash | Connections dropped | Multiple instances, clients reconnect | Clients reconnect with backoff |
| AI / LLM | API timeout | AI assistant unavailable | Timeout + fallback message | User retries |
| RAG / pgvector | Slow query | High AI latency | Query timeout, fallback to tools-only | Cache warm-up |

---

## 14.2 External API Failure Handling

### Circuit Breaker

```python
# sports_platform/providers/circuit_breaker.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Per-provider circuit breaker.
    - CLOSED: all requests pass through
    - OPEN: all requests fail fast (no calls to provider)
    - HALF_OPEN: one test request allowed every 5 minutes
    """
    
    name: str
    failure_threshold: int = 5
    recovery_timeout: timedelta = timedelta(minutes=5)
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_at: datetime = field(default=None, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def call(self, func, *args, **kwargs):
        with self._lock:
            if self._state == CircuitState.OPEN:
                if datetime.utcnow() - self._last_failure_at > self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise ProviderCircuitOpenError(f"Circuit open for {self.name}")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_at = datetime.utcnow()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                # Emit metric: provider.circuit_open
```

---

## 14.3 Kafka Consumer Reliability

### At-Least-Once Processing

Kafka consumers use **manual offset commit** with at-least-once delivery:

```python
# sports_platform/kafka/base_consumer.py

class BaseKafkaConsumer:
    def __init__(self, topics, group_id, config):
        self._consumer = KafkaConsumer(
            *topics,
            group_id=group_id,
            enable_auto_commit=False,   # Manual commit for reliability
            auto_offset_reset="earliest",
            **config,
        )

    def run(self):
        for message in self._consumer:
            try:
                self.process(message)
                self._consumer.commit()  # Only commit after successful processing
            except PermanentError as e:
                # Send to DLQ, then commit (do not block partition)
                self._send_to_dlq(message, e)
                self._consumer.commit()
            except TransientError as e:
                # Log and retry (do not commit — will re-process on restart)
                logger.warning("Transient error, will retry", extra={"error": str(e)})
                time.sleep(self._backoff())
```

### Idempotency Pattern

```python
# Dedup key check before processing any event
def process(self, message):
    event_id = message.value["event_id"]
    dedup_key = f"dedup:event:{event_id}"
    
    # Atomic check-and-set
    acquired = redis_client.setnx(dedup_key, "1")
    if not acquired:
        logger.info("Duplicate event, skipping", extra={"event_id": event_id})
        return  # Already processed

    redis_client.expire(dedup_key, 86400)  # 24h TTL
    
    # Now process safely
    self._process_event(message.value)
```

---

## 14.4 Redis Failure Handling

### Sentinel Configuration (Initial Scale)

```
Redis Sentinel: 1 master + 2 replicas + 3 sentinel processes
- Master handles writes (match:score, pub/sub publish)
- Replicas handle reads (match metadata, odds)
- Sentinels monitor and perform automatic failover

On master failure:
  → Sentinel promotes replica to master in < 30 seconds
  → Application reconnects (redis-py handles this automatically)
  → In-flight pub/sub messages during failover: lost (fire-and-forget acceptable)
  → Connected WebSocket clients: get stale data for < 30s, then resume
```

### Graceful Degradation on Redis Miss

```python
def get_live_score(match_id: str) -> dict:
    """Try Redis first; fall back to PostgreSQL."""
    try:
        score = redis_client.hgetall(f"match:score:{match_id}")
        if score:
            return deserialize_score(score)
    except redis.RedisError as e:
        logger.warning("Redis read failed, falling back to DB", extra={"error": str(e)})
        metrics.increment("redis.fallback")

    # Fallback: PostgreSQL (slower but always available)
    score = MatchScore.objects.get(match_id=match_id)
    return score.score_data
```

---

## 14.5 Out-of-Order Event Handling

```python
# Score updates: reject older sequence numbers (see Redis Lua script in realtime doc)

# Match events: store all events; use event_sequence for ordering on read
# If event_sequence 45 arrives before sequence 44:
#   - Store event 45 in DB (with its sequence number)
#   - Store event 44 when it arrives
#   - API returns events sorted by event_sequence
#   - Client renders in event_sequence order, never display order

# PostgreSQL query: always order by event_sequence
MatchEvent.objects.filter(match_id=match_id).order_by("event_sequence")
```

---

## 14.6 Retry Strategies by Component

### Ingestion Workers (Celery)

```python
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute between retries
    autoretry_for=(httpx.HTTPError, httpx.TimeoutException),
    retry_backoff=True,       # Exponential: 1m, 2m, 4m
    retry_backoff_max=600,    # Cap at 10 minutes
)
def ingest_live_scores_task(self, sport: str, provider: str):
    ...
```

### Kafka Producer Retries

```python
producer_config = {
    "retries": 5,
    "retry_backoff_ms": 500,
    "acks": "all",              # Wait for all replicas to acknowledge
    "enable_idempotence": True, # Exactly-once producer guarantee
}
```

### AI / LLM Timeout

```python
@shared_task(
    time_limit=30,       # Hard kill after 30 seconds
    soft_time_limit=25,  # Graceful shutdown signal at 25 seconds
)
async def ask_match_assistant(conversation_id: str, question: str):
    try:
        result = await run_langgraph_with_timeout(question, timeout=20)
    except asyncio.TimeoutError:
        return {
            "answer": "I'm having trouble fetching that information right now. Please try again.",
            "error": "timeout",
        }
```

---

## 14.7 Dead-Letter Queue Operations

```bash
# DLQ monitoring: alert if any DLQ has > 100 messages
# (defined in Grafana alert rules)

# Manual DLQ inspection
python manage.py inspect_dlq --topic sports.match.event.dlq --limit 10

# Replay from DLQ after fixing root cause
python manage.py replay_dlq \
  --topic sports.match.event.dlq \
  --target sports.match.event \
  --filter "error_type=validation_error" \
  --dry-run  # Preview first

python manage.py replay_dlq \
  --topic sports.match.event.dlq \
  --target sports.match.event \
  --limit 50
```

---

## 14.8 Provider Rate Limit Handling

```python
def call_provider_with_rate_limit(provider, func, *args):
    """
    Handles 429 Too Many Requests from provider APIs.
    Backs off using Retry-After header if provided.
    """
    try:
        return func(*args)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            retry_after = int(e.response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited by {provider}, backing off {retry_after}s")
            metrics.increment(f"provider.rate_limited.{provider}")
            # Don't crash the worker; just skip this cycle
            raise ProviderRateLimitError(retry_after=retry_after)
        raise
```

---

## 14.9 Health Checks

```
GET /health        → 200 if service is up (lightweight, always fast)
GET /health/ready  → 200 only if all dependencies are reachable:
                     - PostgreSQL connection
                     - Redis connection  
                     - Kafka producer connection

Used by:
  - Docker Compose health checks
  - Load balancer health probes
  - Kubernetes liveness/readiness probes (future)
```
