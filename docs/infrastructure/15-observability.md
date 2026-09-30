# 15. Observability

## 15.1 Three Pillars

| Pillar | Tool | Purpose |
|---|---|---|
| **Logs** | Structlog → Loki | Application events, errors, audit trail |
| **Metrics** | Prometheus + Grafana | Counters, gauges, histograms |
| **Traces** | OpenTelemetry → Jaeger (or Tempo) | Distributed request tracing |

---

## 15.2 Structured Logging

All application logs are emitted as **structured JSON** via `structlog`:

```python
# sports_platform/core/logging.py

import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.CallsiteParameterAdder([
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.LINENO,
        ]),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

# Usage:
logger.info(
    "score_updated",
    match_id=match_id,
    sport="cricket",
    sequence_number=892,
    home_score=145,
    latency_ms=12,
)
```

### Log Fields (Standard)

Every log entry includes:
- `timestamp`: ISO 8601
- `level`: debug/info/warning/error/critical
- `service`: api/ws_gateway/ingestion_worker/kafka_consumer
- `trace_id`: OpenTelemetry trace ID (for correlation)
- `user_id`: when in a user request context
- `match_id`: when processing match data

---

## 15.3 Metrics

### Prometheus Metrics

```python
# sports_platform/core/metrics.py

from prometheus_client import Counter, Histogram, Gauge, Summary

# API Metrics
api_request_total = Counter(
    "api_request_total",
    "Total API requests",
    ["method", "endpoint", "status_code"],
)
api_request_duration = Histogram(
    "api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)

# Kafka Metrics
kafka_messages_consumed = Counter(
    "kafka_messages_consumed_total",
    "Total Kafka messages consumed",
    ["topic", "consumer_group", "status"],  # status: processed/skipped/dlq
)
kafka_consumer_lag = Gauge(
    "kafka_consumer_lag",
    "Kafka consumer lag (messages behind)",
    ["topic", "consumer_group", "partition"],
)
kafka_processing_duration = Histogram(
    "kafka_message_processing_seconds",
    "Kafka message processing time",
    ["topic"],
)

# WebSocket Metrics
websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Current active WebSocket connections",
    ["gateway_instance"],
)
websocket_messages_sent = Counter(
    "websocket_messages_sent_total",
    "WebSocket messages sent to clients",
    ["message_type"],
)

# Provider Metrics
provider_requests_total = Counter(
    "provider_requests_total",
    "Total requests to external providers",
    ["provider", "sport", "status"],  # status: success/error/rate_limited
)
provider_latency = Histogram(
    "provider_request_duration_seconds",
    "External provider request latency",
    ["provider"],
)
provider_circuit_state = Gauge(
    "provider_circuit_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["provider"],
)

# Redis Metrics
redis_operations = Counter(
    "redis_operations_total",
    "Redis operations",
    ["operation", "key_prefix", "result"],  # result: hit/miss/error
)

# AI Metrics
ai_requests_total = Counter(
    "ai_requests_total",
    "AI assistant requests",
    ["status"],  # success/timeout/error
)
ai_latency = Histogram(
    "ai_request_duration_seconds",
    "AI assistant response time",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0],
)
ai_tokens_used = Counter(
    "ai_tokens_used_total",
    "LLM tokens consumed",
    ["model", "type"],  # type: input/output
)
rag_retrieval_latency = Histogram(
    "rag_retrieval_duration_seconds",
    "RAG retrieval time",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

# Data Freshness
score_freshness_seconds = Gauge(
    "score_freshness_seconds",
    "Seconds since last score update per sport",
    ["sport"],
)
```

---

## 15.4 Distributed Tracing

```python
# sports_platform/core/tracing.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Spans automatically created for:
# - Django HTTP requests (via opentelemetry-instrumentation-django)
# - PostgreSQL queries (via opentelemetry-instrumentation-psycopg2)
# - Redis calls (via opentelemetry-instrumentation-redis)
# - httpx calls to providers (via opentelemetry-instrumentation-httpx)

# Custom spans for business operations:
tracer = trace.get_tracer("sports_platform")

def process_score_update(event: dict):
    with tracer.start_as_current_span("score_update_processing") as span:
        span.set_attribute("match_id", event["payload"]["match_id"])
        span.set_attribute("sequence_number", event["payload"]["sequence_number"])
        # ... processing logic
```

**Trace flows:**
- `POST /ai/matches/{id}/ask` → intent classification → tool calls (parallel) → RAG retrieval → LLM call → validation → response
- `GET /feed` → Redis cache check → (miss) → PostgreSQL query → Redis update → serialize → response
- Kafka event → consumer → dedup check → DB write → Redis update → pub/sub publish

---

## 15.5 Kafka Consumer Lag Monitoring

```python
# Exported to Prometheus every 30s by a dedicated metrics task

from confluent_kafka.admin import AdminClient

def collect_consumer_lag():
    admin = AdminClient({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})
    consumer_groups = [
        "match-processor", "score-processor", "event-processor",
        "odds-processor", "notification-processor", "notification-delivery",
    ]
    
    for group in consumer_groups:
        offsets = admin.list_consumer_group_offsets(group)
        for partition, offset_info in offsets.items():
            lag = offset_info.high_watermark - offset_info.offset
            kafka_consumer_lag.labels(
                topic=partition.topic,
                consumer_group=group,
                partition=str(partition.partition),
            ).set(lag)
```

---

## 15.6 Dashboards (Grafana)

### Live Sports Dashboard
- Active live matches count
- Score freshness per sport (heatmap)
- Active WebSocket connections
- Events processed per minute per topic
- Consumer lag per consumer group

### API Health Dashboard
- Request rate by endpoint
- p50/p95/p99 response times
- Error rate by endpoint
- Rate limit hits

### AI Dashboard
- AI requests per hour
- p50/p95 AI response latency
- Token usage (input + output) per model
- RAG retrieval p95 latency
- AI error rate

### Provider Dashboard
- Provider uptime per provider
- Request success rate per provider
- Circuit breaker state
- Provider latency p95

---

## 15.7 Alerts

| Alert | Condition | Severity | Action |
|---|---|---|---|
| Score data stale | `score_freshness_seconds > 120` for any live match | Critical | PagerDuty, check provider |
| Consumer lag high | `kafka_consumer_lag > 1000` for any consumer group | Warning | Scale consumer instances |
| Consumer lag critical | `kafka_consumer_lag > 10000` | Critical | PagerDuty, scale immediately |
| DLQ depth growing | DLQ message count increasing over 15 min | Warning | Investigate DLQ messages |
| Provider circuit open | `provider_circuit_state == 1` | Warning | Check provider status |
| API error rate high | `error_rate > 5%` over 5 min | Warning | Check logs |
| API p99 latency high | `api_p99 > 2s` over 5 min | Warning | Check DB/Redis |
| WebSocket connections drop | Sudden drop > 20% in 2 min | Warning | Check gateway health |
| AI latency critical | `ai_p95 > 15s` | Warning | Check LLM API status |
| Redis memory high | `redis_memory_used > 80%` | Warning | Review eviction policy |
| DLQ not empty | Any DLQ message after 30 min | Warning | Investigate + replay |

---

## 15.8 Health Check Endpoint

```python
# sports_platform/api/views/health.py

class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class ReadinessView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        checks = {}
        overall = True

        # PostgreSQL
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["postgresql"] = "ok"
        except Exception as e:
            checks["postgresql"] = str(e)
            overall = False

        # Redis
        try:
            redis_client.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = str(e)
            overall = False

        # Kafka producer
        try:
            kafka_producer.poll(timeout=1)
            checks["kafka"] = "ok"
        except Exception as e:
            checks["kafka"] = str(e)
            overall = False

        status = 200 if overall else 503
        return Response({"status": "ready" if overall else "degraded", "checks": checks}, status=status)
```
