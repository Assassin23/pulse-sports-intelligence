# 20. Repository Structure

```
sports-intelligence-platform/
│
├── README.md
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml         # ruff, black, mypy, detect-secrets
├── pyproject.toml                  # project metadata + tool config
├── requirements/
│   ├── base.txt                    # shared dependencies
│   ├── local.txt                   # dev tools (debugpy, factory-boy, etc.)
│   └── production.txt              # production only (gunicorn, sentry-sdk)
│
├── manage.py
│
# ─── Core Django Application ──────────────────────────────────────────────────
│
├── sports_platform/
│   ├── __init__.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── celery.py                   # Celery app definition
│   │
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py                 # shared settings
│   │   ├── local.py                # local dev overrides
│   │   ├── production.py           # production overrides
│   │   └── test.py                 # test-specific settings
│   │
│   ├── urls.py                     # root URL config
│   │
│   # ─── Django Apps (Domain Modules) ────────────────────────────────────────
│   │
│   ├── users/
│   │   ├── models.py               # User, RefreshToken
│   │   ├── serializers.py          # Register, Login, UserProfile
│   │   ├── views.py                # Auth views (register, login, refresh, logout)
│   │   ├── services.py             # UserService (business logic)
│   │   ├── jwt.py                  # JWT helpers (issue, verify, blacklist)
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   └── tests/
│   │       ├── test_models.py
│   │       └── test_views.py
│   │
│   ├── preferences/
│   │   ├── models.py               # UserSportPreference, UserFollowedEntity, UserNotificationPreference
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── services.py             # PreferenceService
│   │   ├── urls.py
│   │   ├── apps.py
│   │   └── tests/
│   │
│   ├── sports/
│   │   ├── models.py               # Sport, Country, Team, Competition, Player, ProviderEntityMapping
│   │   ├── serializers.py
│   │   ├── views.py                # Sports search endpoints
│   │   ├── services.py
│   │   ├── admin.py
│   │   ├── urls.py
│   │   ├── apps.py
│   │   ├── management/
│   │   │   └── commands/
│   │   │       ├── seed_sports.py  # Load sports, countries
│   │   │       └── seed_fixtures.py
│   │   └── tests/
│   │
│   ├── matches/
│   │   ├── models.py               # Match, MatchScore, MatchEvent, MatchStatistic
│   │   ├── serializers.py
│   │   ├── views.py                # Matches, events, statistics endpoints
│   │   ├── services/
│   │   │   ├── match_service.py    # MatchService (queries, state management)
│   │   │   ├── score_service.py    # ScoreService (Redis + DB read)
│   │   │   └── event_service.py    # EventService (recent events)
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   └── tests/
│   │
│   ├── feed/
│   │   ├── services.py             # FeedService (assemble personalized feed)
│   │   ├── serializers.py
│   │   ├── views.py                # GET /feed
│   │   ├── urls.py
│   │   ├── apps.py
│   │   └── tests/
│   │
│   ├── odds/
│   │   ├── models.py               # MatchOddsCurrent, MatchOddsHistory
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── services.py             # OddsService
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   └── tests/
│   │
│   ├── notifications/
│   │   ├── models.py               # NotificationLog
│   │   ├── services/
│   │   │   ├── fanout.py           # NotificationFanout
│   │   │   └── delivery.py         # WebSocket + Push delivery
│   │   ├── push/
│   │   │   ├── base.py             # PushProvider ABC
│   │   │   └── fcm.py              # FCM implementation
│   │   ├── tasks.py                # Celery tasks
│   │   ├── views.py                # Notification preferences API
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── apps.py
│   │   └── tests/
│   │
│   ├── ai/
│   │   ├── models.py               # AIConversation, AIMessage
│   │   ├── serializers.py
│   │   ├── views.py                # POST /ai/matches/{id}/ask
│   │   ├── services.py             # ConversationService
│   │   ├── security.py             # Input sanitization
│   │   ├── urls.py
│   │   ├── graph/
│   │   │   ├── __init__.py
│   │   │   ├── state.py            # AssistantState TypedDict
│   │   │   ├── graph.py            # LangGraph graph builder
│   │   │   └── nodes/
│   │   │       ├── __init__.py
│   │   │       ├── intent_classifier.py
│   │   │       ├── data_planner.py
│   │   │       ├── backend_tools.py     # Tool execution
│   │   │       ├── rag_retrieval.py
│   │   │       ├── synthesizer.py       # LLM call
│   │   │       ├── validator.py
│   │   │       └── responder.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── get_live_score.py
│   │   │   ├── get_match_events.py
│   │   │   ├── get_team_stats.py
│   │   │   ├── get_standings.py
│   │   │   ├── get_recent_matches.py
│   │   │   └── search_knowledge_base.py
│   │   ├── llm.py                  # LLM client factory (pluggable provider)
│   │   ├── apps.py
│   │   └── tests/
│   │
│   ├── rag/
│   │   ├── models.py               # RAGDocument, RAGChunk
│   │   ├── ingestion/
│   │   │   ├── pipeline.py         # DocumentIngestionPipeline
│   │   │   ├── sources/
│   │   │   │   ├── base.py         # DocumentSource ABC
│   │   │   │   ├── manual.py       # Upload via admin/API
│   │   │   │   └── web_scraper.py  # Optional: scrape team/player pages
│   │   │   └── tasks.py            # Celery async ingestion tasks
│   │   ├── chunking/
│   │   │   └── semantic_chunker.py
│   │   ├── embeddings/
│   │   │   ├── base.py             # Embedder ABC
│   │   │   └── openai_embedder.py
│   │   ├── retrieval/
│   │   │   ├── retriever.py        # HybridRetriever
│   │   │   └── reranker.py         # Cohere/CrossEncoder reranker
│   │   ├── views.py                # Admin: ingest document endpoint
│   │   ├── admin.py
│   │   ├── urls.py
│   │   ├── apps.py
│   │   └── tests/
│   │
│   # ─── Infrastructure / Cross-Cutting ──────────────────────────────────────
│   │
│   ├── kafka/
│   │   ├── __init__.py
│   │   ├── producer.py             # KafkaEventProducer (singleton)
│   │   ├── topics.py               # Topic name constants
│   │   ├── schemas.py              # Event dataclasses / Pydantic models
│   │   ├── base_consumer.py        # BaseKafkaConsumer (retry, DLQ, dedup)
│   │   ├── consumers/
│   │   │   ├── __init__.py
│   │   │   ├── match_processor.py
│   │   │   ├── score_processor.py
│   │   │   ├── event_processor.py
│   │   │   ├── odds_processor.py
│   │   │   ├── notification_processor.py
│   │   │   ├── notification_delivery.py
│   │   │   └── feed_invalidation.py
│   │   └── management/
│   │       └── commands/
│   │           ├── run_kafka_consumers.py   # Starts all consumers
│   │           ├── create_kafka_topics.py   # Topic creation on startup
│   │           └── replay_dlq.py            # DLQ replay utility
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                 # SportsDataProvider, OddsDataProvider ABCs
│   │   ├── registry.py             # ProviderRegistry
│   │   ├── circuit_breaker.py      # CircuitBreaker
│   │   ├── exceptions.py
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── api_football.py     # ApiFootballAdapter
│   │   │   ├── cricbuzz.py         # CricbuzzAdapter
│   │   │   └── odds_provider.py    # OddsProviderAdapter
│   │   └── normalization.py        # Shared normalization utilities
│   │
│   ├── ingestion/
│   │   ├── workers/
│   │   │   ├── sports_ingestion_worker.py
│   │   │   └── odds_ingestion_worker.py
│   │   └── tasks.py                # Celery Beat scheduled tasks
│   │
│   ├── cache/
│   │   ├── client.py               # Redis client factory (cache + auth instances)
│   │   ├── keys.py                 # Redis key name constants
│   │   └── helpers.py              # Common Redis operations
│   │
│   ├── core/
│   │   ├── logging.py              # Structlog configuration
│   │   ├── metrics.py              # Prometheus metrics registry
│   │   ├── tracing.py              # OpenTelemetry setup
│   │   ├── exceptions.py           # Domain exceptions
│   │   └── middleware/
│   │       ├── rate_limiting.py
│   │       ├── request_id.py       # Adds X-Request-ID header
│   │       └── audit_logging.py
│   │
│   └── api/
│       ├── __init__.py
│       ├── views/
│       │   └── health.py           # /health, /health/ready
│       ├── pagination.py           # Cursor pagination
│       ├── permissions.py          # Custom DRF permissions
│       └── throttling.py           # Custom DRF throttle classes
│
# ─── WebSocket Gateway (Separate Service) ────────────────────────────────────
│
├── ws_gateway/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app
│   ├── auth.py                     # JWT verification (shared public key)
│   ├── redis_client.py             # Async Redis client
│   ├── health.py                   # /health endpoint
│   └── tests/
│       └── test_websocket.py
│
# ─── Tests ───────────────────────────────────────────────────────────────────
│
├── tests/
│   ├── conftest.py                 # Shared fixtures (db, redis, kafka, mock providers)
│   ├── factories.py                # Factory Boy model factories
│   ├── fixtures/
│   │   └── vcr_cassettes/          # VCR recorded HTTP responses for provider tests
│   ├── unit/
│   │   ├── test_score_processor.py
│   │   ├── test_api_football_adapter.py
│   │   ├── test_odds_normalization.py
│   │   ├── test_notification_fanout.py
│   │   └── test_rag_chunker.py
│   ├── api/
│   │   ├── test_auth.py
│   │   ├── test_feed.py
│   │   ├── test_matches.py
│   │   ├── test_odds.py
│   │   ├── test_preferences.py
│   │   └── test_ai_assistant.py
│   ├── integration/
│   │   ├── test_kafka_consumers.py
│   │   ├── test_redis_state.py
│   │   └── test_ingestion_pipeline.py
│   ├── ai/
│   │   ├── test_langgraph_graph.py
│   │   ├── test_ai_tools.py
│   │   └── test_rag_retrieval.py
│   ├── websocket/
│   │   └── test_ws_gateway.py
│   └── load/
│       └── locustfile.py
│
# ─── Infrastructure / Docker ─────────────────────────────────────────────────
│
├── docker/
│   ├── api/
│   │   └── Dockerfile
│   ├── ws_gateway/
│   │   └── Dockerfile
│   ├── postgres/
│   │   └── init.sql
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── grafana/
│       ├── dashboards/
│       │   ├── api_health.json
│       │   ├── kafka_consumers.json
│       │   └── ai_metrics.json
│       └── datasources/
│           └── datasources.yml
│
├── docker-compose.yml              # Local development
├── docker-compose.ci.yml           # CI environment
├── docker-compose.prod.yml         # Production (or reference)
│
# ─── Documentation ───────────────────────────────────────────────────────────
│
└── docs/
    ├── 01-overview-and-requirements.md
    ├── architecture/
    │   ├── 02-high-level-architecture.md
    │   ├── 03-event-driven-architecture.md
    │   ├── 06-provider-architecture.md
    │   ├── 07-realtime-architecture.md
    │   ├── 08-odds-architecture.md
    │   └── 13-notifications.md
    ├── data-model/
    │   ├── 04-database-design.md
    │   └── 05-redis-design.md
    ├── api/
    │   ├── 11-api-design.md
    │   └── 12-auth-and-security.md
    ├── ai/
    │   ├── 09-ai-rag-architecture.md
    │   └── 10-langgraph-workflow.md
    └── infrastructure/
        ├── 14-reliability.md
        ├── 15-observability.md
        ├── 16-testing-strategy.md
        ├── 17-docker-local-dev.md
        ├── 18-production-deployment.md
        └── 19-scalability-strategy.md
```
