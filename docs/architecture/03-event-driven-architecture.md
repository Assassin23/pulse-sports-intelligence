# 3. Event-Driven Architecture

## 3.1 Design Principles

- **Kafka is the source of truth for the ingestion pipeline.** Every event ingested from a provider is published to Kafka before any processing occurs.
- **Consumers are idempotent.** Every consumer checks a deduplication key before writing. Reprocessing the same event must be safe.
- **Out-of-order events are handled.** Each event carries a `source_timestamp` and `sequence_number`. Processors apply optimistic concurrency checks before updating state.
- **Dead-letter queues (DLQ) exist for every topic.** Poisoned messages are moved to `<topic>.dlq` after `max_retries` exhausted.
- **Kafka is not used as a database.** Redis and PostgreSQL hold state. Kafka is the transport.

---

## 3.2 Topic Registry

| Topic | Partitions | Replication | Retention |
|---|---|---|---|
| `sports.match.discovered` | 12 | 3 | 7 days |
| `sports.match.started` | 12 | 3 | 7 days |
| `sports.score.updated` | 24 | 3 | 2 days |
| `sports.match.event` | 24 | 3 | 7 days |
| `sports.match.completed` | 12 | 3 | 7 days |
| `sports.odds.updated` | 12 | 3 | 1 day |
| `sports.user.preference.updated` | 6 | 3 | 3 days |
| `notifications.requested` | 12 | 3 | 1 day |
| `*.dlq` | 3 | 3 | 14 days |

**Partition key rule:** All match-related topics partition by `match_id`. This guarantees ordering of events for the same match within a partition.

---

## 3.3 Event Contracts

### 3.3.1 `sports.match.discovered`

**Producer:** Sports Ingestion Worker  
**Consumer:** Match Processor (Django consumer)  
**Partitioning:** `match_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "sports.match.discovered",
  "schema_version": "1.0",
  "source_provider": "provider_a",
  "source_timestamp": "2026-09-30T10:00:00Z",
  "produced_at": "2026-09-30T10:00:05Z",
  "payload": {
    "match_id": "ext-provider-a-12345",
    "internal_match_id": null,
    "sport": "cricket",
    "competition": {
      "id": "ext-ipl-2026",
      "name": "Indian Premier League 2026",
      "country": "India"
    },
    "home_team": {
      "id": "ext-rcb",
      "name": "Royal Challengers Bengaluru",
      "country": "India"
    },
    "away_team": {
      "id": "ext-mi",
      "name": "Mumbai Indians",
      "country": "India"
    },
    "scheduled_at": "2026-10-01T14:00:00Z",
    "venue": "M. Chinnaswamy Stadium, Bengaluru",
    "status": "scheduled"
  }
}
```

**Idempotency key:** `(source_provider, match_id)` — unique constraint in PostgreSQL `matches` table.  
**Ordering:** Not critical (match only discovered once per provider).  
**Retry strategy:** 3 retries with exponential backoff (1s, 2s, 4s). After 3 failures → DLQ.  
**DLQ:** `sports.match.discovered.dlq`

---

### 3.3.2 `sports.match.started`

**Producer:** Sports Ingestion Worker  
**Consumer:** Match Processor, Notification Processor  
**Partitioning:** `match_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "sports.match.started",
  "schema_version": "1.0",
  "source_provider": "provider_a",
  "source_timestamp": "2026-10-01T14:02:30Z",
  "produced_at": "2026-10-01T14:02:35Z",
  "payload": {
    "match_id": "ext-provider-a-12345",
    "sport": "cricket",
    "status": "live",
    "started_at": "2026-10-01T14:02:30Z"
  }
}
```

**Idempotency key:** `(source_provider, match_id, event_type)` stored in Redis set `processed_events:{match_id}`.  
**Ordering:** Must arrive after `match.discovered`. Processor re-queues with 10s delay if match not found.

---

### 3.3.3 `sports.score.updated`

**Producer:** Sports Ingestion Worker (high frequency: every 30s for live matches)  
**Consumer:** Score Processor  
**Partitioning:** `match_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "sports.score.updated",
  "schema_version": "1.0",
  "source_provider": "provider_a",
  "source_timestamp": "2026-10-01T15:30:00Z",
  "produced_at": "2026-10-01T15:30:02Z",
  "payload": {
    "match_id": "ext-provider-a-12345",
    "sport": "cricket",
    "score": {
      "home": {
        "team_id": "ext-rcb",
        "runs": 145,
        "wickets": 3,
        "overs": "15.2"
      },
      "away": {
        "team_id": "ext-mi",
        "runs": 0,
        "wickets": 0,
        "overs": "0.0"
      },
      "innings": 1,
      "current_partnership": {
        "runs": 62,
        "balls": 38
      }
    },
    "sequence_number": 892
  }
}
```

**Idempotency:** `sequence_number` — processor skips update if stored `sequence_number` >= incoming.  
**Ordering:** Enforced by `sequence_number`. Out-of-order messages are discarded (not reprocessed).  
**Volume:** ~100 live matches × 2 updates/min = 200 events/min peak. Very manageable.  
**Retry strategy:** 3 retries. Score updates are idempotent; latest wins. No DLQ for score updates (stale is acceptable).

---

### 3.3.4 `sports.match.event`

**Producer:** Sports Ingestion Worker  
**Consumer:** Event Processor, Notification Processor  
**Partitioning:** `match_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "sports.match.event",
  "schema_version": "1.0",
  "source_provider": "provider_a",
  "source_timestamp": "2026-10-01T15:32:10Z",
  "produced_at": "2026-10-01T15:32:12Z",
  "payload": {
    "match_id": "ext-provider-a-12345",
    "sport": "cricket",
    "event_sequence": 45,
    "event_type": "wicket",
    "minute": null,
    "over": "16.3",
    "description": "Kohli c Rohit b Bumrah 0 (1b)",
    "player": {
      "id": "ext-virat-kohli",
      "name": "Virat Kohli",
      "team_id": "ext-rcb"
    },
    "bowler": {
      "id": "ext-jasprit-bumrah",
      "name": "Jasprit Bumrah",
      "team_id": "ext-mi"
    },
    "score_after": {
      "runs": 145,
      "wickets": 4,
      "overs": "16.3"
    }
  }
}
```

**Idempotency key:** `(source_provider, match_id, event_sequence)` — unique constraint in PostgreSQL `match_events` table.  
**Ordering:** `event_sequence` determines order. Events stored with sequence; UI renders in order.  
**DLQ:** `sports.match.event.dlq` — manual review required (event loss is unacceptable).

---

### 3.3.5 `sports.match.completed`

**Producer:** Sports Ingestion Worker  
**Consumer:** Match Processor, Notification Processor  
**Partitioning:** `match_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "sports.match.completed",
  "schema_version": "1.0",
  "source_provider": "provider_a",
  "source_timestamp": "2026-10-01T17:45:00Z",
  "produced_at": "2026-10-01T17:45:02Z",
  "payload": {
    "match_id": "ext-provider-a-12345",
    "sport": "cricket",
    "result": {
      "winner_team_id": "ext-rcb",
      "result_description": "RCB won by 23 runs",
      "final_scores": {
        "home": {"runs": 198, "wickets": 6, "overs": "20.0"},
        "away": {"runs": 175, "wickets": 9, "overs": "20.0"}
      }
    },
    "completed_at": "2026-10-01T17:45:00Z"
  }
}
```

**Idempotency key:** `(source_provider, match_id, event_type)`.  
**Post-processing:** Redis TTL for match state reduced to 6 hours after completion. Match state marked `completed`.

---

### 3.3.6 `sports.odds.updated`

**Producer:** Odds Ingestion Worker  
**Consumer:** Odds Processor  
**Partitioning:** `match_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "sports.odds.updated",
  "schema_version": "1.0",
  "source_provider": "odds_provider_x",
  "source_timestamp": "2026-10-01T14:00:00Z",
  "produced_at": "2026-10-01T14:00:01Z",
  "payload": {
    "match_id": "ext-provider-a-12345",
    "sport": "cricket",
    "market": "match_winner",
    "odds": [
      {"outcome": "home_win", "value": 1.85, "currency": "decimal"},
      {"outcome": "away_win", "value": 2.10, "currency": "decimal"}
    ],
    "bookmaker": "Bet365",
    "odds_timestamp": "2026-10-01T14:00:00Z"
  }
}
```

**Idempotency:** `(source_provider, match_id, market, odds_timestamp)` unique in `odds_history` table. Same timestamp + same values = no-op.

---

### 3.3.7 `sports.user.preference.updated`

**Producer:** Django API (on preference save)  
**Consumer:** Feed Invalidation Consumer  
**Partitioning:** `user_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "sports.user.preference.updated",
  "schema_version": "1.0",
  "produced_at": "2026-09-30T10:00:00Z",
  "payload": {
    "user_id": "user-uuid-123",
    "change_type": "added",
    "sport": "cricket",
    "entity_type": "team",
    "entity_id": "team-rcb-internal"
  }
}
```

**Consumer action:** Invalidate Redis feed cache key `feed:{user_id}`. Next feed request rebuilds from PostgreSQL.

---

### 3.3.8 `notifications.requested`

**Producer:** Notification Processor (downstream of match event consumer)  
**Consumer:** Notification Delivery Worker  
**Partitioning:** `user_id`

```json
{
  "event_id": "uuid-v4",
  "event_type": "notifications.requested",
  "schema_version": "1.0",
  "produced_at": "2026-10-01T15:32:13Z",
  "payload": {
    "user_id": "user-uuid-123",
    "notification_type": "wicket",
    "match_id": "internal-match-uuid",
    "title": "Wicket! 🏏",
    "body": "Virat Kohli is out! RCB 145/4 in 16.3 overs.",
    "channels": ["websocket", "push"],
    "priority": "high",
    "ttl_seconds": 300
  }
}
```

---

## 3.4 Consumer Group Strategy

| Consumer Group | Topics Consumed | Instances |
|---|---|---|
| `match-processor` | `sports.match.discovered`, `sports.match.started`, `sports.match.completed` | 2-4 |
| `score-processor` | `sports.score.updated` | 4-8 (high volume) |
| `event-processor` | `sports.match.event` | 2-4 |
| `odds-processor` | `sports.odds.updated` | 2 |
| `notification-processor` | `sports.match.event`, `sports.match.started`, `sports.match.completed` | 2-4 |
| `notification-delivery` | `notifications.requested` | 4 |
| `feed-invalidation` | `sports.user.preference.updated` | 1 |

---

## 3.5 Error Handling & DLQ Flow

```
Consumer reads message
  → Processing attempt 1 → failure
  → Wait 1s → attempt 2 → failure
  → Wait 2s → attempt 3 → failure
  → Publish to <topic>.dlq with metadata:
      { original_topic, original_offset, error_type, error_message, failed_at, retry_count }
  → Commit original topic offset (do not block healthy partition)

DLQ monitoring:
  → Alert if DLQ depth > 100 messages
  → Ops engineer inspects, fixes root cause, replays from DLQ
  → DLQ replay script: python manage.py replay_dlq --topic sports.match.event.dlq
```
