# 18. Production Deployment

## 18.1 Philosophy

Start simple. Evolve as needed. A small team should be able to deploy and operate this system without a DevOps engineer or a Kubernetes cluster.

**Initial target:** Single cloud provider (AWS, GCP, or Railway/Render), VMs + managed services.

---

## 18.2 Initial Production Topology (10K Users)

```
                           ┌─────────────────────────────────────────────┐
                           │          Cloudflare (CDN + DDoS)            │
                           └──────────────────┬──────────────────────────┘
                                              │
                           ┌──────────────────▼──────────────────────────┐
                           │          Load Balancer (Nginx / ALB)         │
                           └────────┬──────────────────────┬─────────────┘
                                    │                      │
                         ┌──────────▼───────┐  ┌──────────▼────────────┐
                         │   API Server(s)  │  │  WebSocket Gateway(s) │
                         │  Django + Gunicorn│  │  FastAPI + Uvicorn    │
                         │   2× t3.medium   │  │   2× t3.small         │
                         └──────────┬───────┘  └──────────┬────────────┘
                                    │                      │
              ┌─────────────────────▼──────────────────────▼──────────────┐
              │                 Shared Services                            │
              │                                                           │
              │  ┌──────────────────┐    ┌──────────────────────────────┐ │
              │  │  PostgreSQL RDS  │    │        Redis (ElastiCache     │ │
              │  │  db.t3.medium    │    │        cache.t3.medium)       │ │
              │  │  + 1 read replica│    │        + 1 replica            │ │
              │  └──────────────────┘    └──────────────────────────────┘ │
              │                                                           │
              │  ┌────────────────────────────────────────────────────┐  │
              │  │   MSK (AWS Managed Kafka) or self-hosted Kafka      │  │
              │  │   3 brokers, 3 AZs                                  │  │
              │  └────────────────────────────────────────────────────┘  │
              └───────────────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────▼──────────────────────────────────┐
              │           Background Services (1× t3.medium)           │
              │  Celery Worker | Celery Beat | Kafka Consumers         │
              │  Sports Ingestion | Odds Ingestion                     │
              └────────────────────────────────────────────────────────┘
```

---

## 18.3 Managed Services Recommendation

| Component | Managed Option | Self-Hosted Option | Recommendation |
|---|---|---|---|
| PostgreSQL | AWS RDS / Supabase | Docker on VM | **Managed** (backups, failover built-in) |
| Redis | AWS ElastiCache / Upstash | Redis Docker | **Managed** (operations overhead low) |
| Kafka | AWS MSK / Confluent Cloud | Docker + KRaft | **Managed MSK** for > 10K users |
| Monitoring | Grafana Cloud | Self-hosted Grafana | Start self-hosted, migrate to Cloud when needed |
| AI (LLM) | OpenAI API / Vertex AI | Ollama (local models) | **Managed** for initial scale |

---

## 18.4 Environment Configuration

```bash
# Production environment variables (stored in AWS Secrets Manager or Fly.io secrets)

DJANGO_SETTINGS_MODULE=sports_platform.settings.production
SECRET_KEY=<strong-random-key>
DEBUG=false
ALLOWED_HOSTS=api.sports-platform.com,ws.sports-platform.com

DATABASE_URL=postgresql://sports:<pass>@rds-endpoint:5432/sports_db
DATABASE_READ_URL=postgresql://sports:<pass>@rds-read-endpoint:5432/sports_db

REDIS_URL=redis://:<pass>@elasticache-endpoint:6379/0
REDIS_AUTH_URL=redis://:<pass>@elasticache-endpoint:6379/1

KAFKA_BOOTSTRAP_SERVERS=b-1.msk.amazonaws.com:9092,b-2.msk.amazonaws.com:9092
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-256
KAFKA_SASL_USERNAME=<msk-user>
KAFKA_SASL_PASSWORD=<msk-password>

OPENAI_API_KEY=<openai-key>
JWT_PRIVATE_KEY=<rsa-private-key-pem>
JWT_PUBLIC_KEY=<rsa-public-key-pem>

PROVIDER_A_API_KEY=<key>
PROVIDER_B_API_KEY=<key>
ODDS_PROVIDER_API_KEY=<key>

FCM_PROJECT_ID=<firebase-project>
FCM_SERVICE_ACCOUNT_JSON=<json>

SENTRY_DSN=<sentry-dsn>
PROMETHEUS_PUSHGATEWAY_URL=<url>
```

---

## 18.5 Process Management

Use **systemd** or **supervisor** on VMs, or **Docker Compose** with restart policies:

```yaml
# docker-compose.prod.yml (simplified, secrets via environment)

services:
  api:
    image: registry.example.com/sports-api:${VERSION}
    command: gunicorn sports_platform.wsgi:application -w 4 -b 0.0.0.0:8000
    restart: always
    deploy:
      replicas: 2
    environment:
      - DJANGO_SETTINGS_MODULE=sports_platform.settings.production

  ws-gateway:
    image: registry.example.com/sports-ws:${VERSION}
    command: uvicorn ws_gateway.main:app --host 0.0.0.0 --port 8001 --workers 2
    restart: always

  worker:
    image: registry.example.com/sports-api:${VERSION}
    command: celery -A sports_platform worker -l info -c 8 --max-tasks-per-child=1000
    restart: always

  beat:
    image: registry.example.com/sports-api:${VERSION}
    command: celery -A sports_platform beat -l info
    restart: always
    deploy:
      replicas: 1  # CRITICAL: only 1 beat instance

  kafka-consumers:
    image: registry.example.com/sports-api:${VERSION}
    command: python manage.py run_kafka_consumers
    restart: always
    deploy:
      replicas: 2
```

---

## 18.6 Nginx Configuration

```nginx
# nginx.conf

upstream django_api {
    server api:8000;
    keepalive 100;
}

upstream ws_gateway {
    server ws-gateway:8001;
    keepalive 100;
}

server {
    listen 443 ssl http2;
    server_name api.sports-platform.com;

    ssl_certificate     /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;

    # API endpoints
    location /api/ {
        proxy_pass http://django_api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }

    # WebSocket upgrades
    location /ws/ {
        proxy_pass http://ws_gateway;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300s;   # Keep WS alive for 5 minutes
        proxy_send_timeout 300s;
    }

    # Health checks (bypass auth)
    location /health {
        proxy_pass http://django_api;
        access_log off;
    }

    # Rate limiting at Nginx level
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
    limit_req zone=api burst=20 nodelay;
}
```

---

## 18.7 CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml

name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: docker compose -f docker-compose.ci.yml run --rm api pytest tests/unit tests/api

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build and push Docker image
        run: |
          docker build -t registry.example.com/sports-api:${{ github.sha }} .
          docker push registry.example.com/sports-api:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          ssh deploy@prod-server "
            cd /opt/sports-platform &&
            VERSION=${{ github.sha }} docker compose -f docker-compose.prod.yml pull &&
            VERSION=${{ github.sha }} docker compose -f docker-compose.prod.yml up -d &&
            docker compose exec -T api python manage.py migrate --no-input
          "
```

---

## 18.8 Backup Strategy

```bash
# PostgreSQL: automated RDS snapshots (daily, 7-day retention)
# Redis: snapshot disabled for cache; AOF enabled for auth Redis
# Kafka: log retention 7 days (events can be replayed)

# Disaster recovery test: quarterly
# RPO (Recovery Point Objective): < 1 hour
# RTO (Recovery Time Objective): < 30 minutes
```
