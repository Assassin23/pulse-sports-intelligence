# 17. Docker & Local Development

## 17.1 Service Topology

| Service | Port | Description |
|---|---|---|
| `api` | 8000 | Django + DRF core API |
| `ws-gateway` | 8001 | FastAPI WebSocket gateway |
| `worker` | — | Celery worker (tasks) |
| `beat` | — | Celery beat (scheduled ingestion) |
| `kafka-consumer` | — | Kafka consumer processes |
| `postgres` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 |
| `kafka` | 9092 | Apache Kafka (KRaft mode, no Zookeeper) |
| `kafka-ui` | 8080 | Kafka UI (provectus/kafka-ui) |
| `prometheus` | 9090 | Metrics collection |
| `grafana` | 3000 | Dashboards (admin/admin) |
| `loki` | 3100 | Log aggregation |

---

## 17.2 Docker Compose

```yaml
# docker-compose.yml

version: "3.9"

x-common-env: &common-env
  DATABASE_URL: postgresql://sports:sports@postgres:5432/sports_db
  REDIS_URL: redis://redis:6379/0
  KAFKA_BOOTSTRAP_SERVERS: kafka:9092
  DJANGO_SETTINGS_MODULE: sports_platform.settings.local
  SECRET_KEY: local-dev-secret-key-not-for-prod
  DEBUG: "true"

x-django-base: &django-base
  build:
    context: .
    dockerfile: docker/api/Dockerfile
  volumes:
    - .:/app
  environment:
    <<: *common-env
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
    kafka:
      condition: service_healthy

services:
  # ─── Core Infrastructure ─────────────────────────────────────────────

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: sports_db
      POSTGRES_USER: sports
      POSTGRES_PASSWORD: sports
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sports -d sports_db"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly no --maxmemory 512mb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  kafka:
    image: confluentinc/cp-kafka:7.6.0
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1  # 1 for local; 3 for prod
      KAFKA_LOG_DIRS: /var/lib/kafka/data
      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
    ports:
      - "9092:9092"
    volumes:
      - kafka_data:/var/lib/kafka/data
    healthcheck:
      test: ["CMD-SHELL", "kafka-topics --bootstrap-server localhost:9092 --list"]
      interval: 10s
      timeout: 5s
      retries: 10

  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
    ports:
      - "8080:8080"
    depends_on:
      kafka:
        condition: service_healthy

  # ─── Application Services ─────────────────────────────────────────────

  api:
    <<: *django-base
    command: >
      sh -c "python manage.py wait_for_db &&
             python manage.py migrate &&
             python manage.py create_kafka_topics &&
             python -m uvicorn sports_platform.asgi:application --host 0.0.0.0 --port 8000 --reload"
    ports:
      - "8000:8000"

  ws-gateway:
    build:
      context: .
      dockerfile: docker/ws_gateway/Dockerfile
    command: uvicorn ws_gateway.main:app --host 0.0.0.0 --port 8001 --reload
    environment:
      <<: *common-env
    ports:
      - "8001:8001"
    volumes:
      - .:/app
    depends_on:
      redis:
        condition: service_healthy

  worker:
    <<: *django-base
    command: celery -A sports_platform worker -l info -Q celery,notifications,ai -c 4
    environment:
      <<: *common-env
      CELERY_BROKER_URL: redis://redis:6379/1

  beat:
    <<: *django-base
    command: celery -A sports_platform beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    environment:
      <<: *common-env
      CELERY_BROKER_URL: redis://redis:6379/1

  kafka-consumers:
    <<: *django-base
    command: python manage.py run_kafka_consumers
    environment:
      <<: *common-env
    deploy:
      replicas: 1

  # ─── Observability ────────────────────────────────────────────────────

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./docker/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./docker/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./docker/grafana/datasources:/etc/grafana/provisioning/datasources

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    volumes:
      - loki_data:/loki

volumes:
  postgres_data:
  redis_data:
  kafka_data:
  grafana_data:
  loki_data:
```

---

## 17.3 Dockerfile (API)

```dockerfile
# docker/api/Dockerfile

FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements/base.txt requirements/local.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/local.txt

# Application code
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
```

---

## 17.4 PostgreSQL Initialization

```sql
-- docker/postgres/init.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";   -- pgvector for RAG embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search
```

---

## 17.5 Local Development Setup

```bash
# 1. Prerequisites
# Docker Desktop, Python 3.12, git

# 2. Clone and configure
git clone <repo>
cd sports-intelligence-platform
cp .env.example .env.local
# Edit .env.local with your API keys (provider, OpenAI)

# 3. Start all services
docker compose up -d

# 4. Wait for services to be healthy
docker compose ps  # All services should show "healthy"

# 5. Run migrations + create topics
docker compose exec api python manage.py migrate
docker compose exec api python manage.py create_kafka_topics

# 6. Load seed data
docker compose exec api python manage.py seed_sports      # Sports, countries
docker compose exec api python manage.py seed_fixtures    # Sample upcoming matches
docker compose exec api python manage.py seed_rag_docs   # Sample RAG documents

# 7. Create superuser
docker compose exec api python manage.py createsuperuser

# 8. Verify
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/matches/live

# 9. Open UIs
# API: http://localhost:8000/api/v1/
# Django Admin: http://localhost:8000/admin/
# Kafka UI: http://localhost:8080/
# Grafana: http://localhost:3000/ (admin/admin)
# Prometheus: http://localhost:9090/
```

---

## 17.6 Simulating Live Data Locally

```bash
# Simulate live match events (useful for testing WebSocket without real provider)
docker compose exec api python manage.py simulate_live_match \
  --sport cricket \
  --interval 5  # Publish an event every 5 seconds

# Watch the Kafka topic in real time
docker compose exec kafka \
  kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic sports.score.updated \
  --from-beginning
```

---

## 17.7 Running Tests Locally

```bash
# Unit + API tests (fast, no external services)
docker compose exec api pytest tests/unit tests/api -v

# Integration tests (requires running Postgres + Redis + Kafka)
docker compose exec api pytest tests/integration -v

# WebSocket tests
docker compose exec ws-gateway pytest tests/websocket -v

# All tests with coverage
docker compose exec api pytest --cov=sports_platform --cov-report=html tests/

# Load tests (ensure services are running)
locust -f tests/load/locustfile.py --host http://localhost:8000
```
