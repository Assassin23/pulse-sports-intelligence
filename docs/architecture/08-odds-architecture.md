# 8. Odds Architecture

## 8.1 Design Principles

- Odds are **informational only**. No betting, wagering, or gambling functionality.
- Multiple odds providers may supply data for the same match/market. All are stored independently.
- Odds are **tracked over time** for display purposes (e.g., line movement charts).
- Current odds are in Redis for fast reads. Historical odds are in PostgreSQL (append-only).
- Odds updates arrive much more frequently than score updates (especially pre-match).

---

## 8.2 Odds Ingestion Flow

```
Odds Provider API (polling)
  │  Pre-match: every 60s
  │  Live (in-play): every 15s
  ▼
Odds Ingestion Worker
  │  Normalizes market types and outcome labels
  │  Computes fingerprint to detect actual changes
  │  Only publishes to Kafka if odds actually changed
  ▼
Kafka: sports.odds.updated
  │  Partitioned by match_id
  ▼
Odds Processor (Django consumer)
  │  1. Idempotency check
  │  2. Write to PostgreSQL match_odds_history (append-only)
  │  3. Upsert PostgreSQL match_odds_current (current state)
  │  4. Update Redis match:odds:{match_id}:{market}
  │  5. Update Redis match:odds:history:{match_id}:{market} (last 10)
  │  6. PUBLISH to Redis ws:match:{match_id} (odds_updated event)
  ▼
WebSocket Gateway → Clients
```

---

## 8.3 Odds Normalization

Different providers use different market names, outcome labels, and odds formats. The adapter normalizes these:

```python
# sports_platform/providers/odds_normalization.py

MARKET_TYPE_MAP = {
    # api-football style
    "Match Winner": "match_winner",
    "Asian Handicap": "handicap",
    "Goals Over/Under": "over_under",
    "Both Teams Score": "both_teams_to_score",
    # other providers
    "1X2": "match_winner",
    "OU": "over_under",
    "AH": "handicap",
}

OUTCOME_LABEL_MAP = {
    "match_winner": {
        "Home": "home_win",
        "Away": "away_win",
        "Draw": "draw",
        "1": "home_win",
        "2": "away_win",
        "X": "draw",
    },
    "over_under": {
        "Over": "over",
        "Under": "under",
    }
}

def normalize_odds_value(value: float, format: str = "decimal") -> float:
    """Convert all odds to decimal format for internal storage."""
    if format == "fractional":
        # e.g., "9/4" → 3.25
        num, den = value.split("/")
        return (int(num) / int(den)) + 1.0
    elif format == "american":
        # e.g., +250 → 3.50, -150 → 1.667
        if value > 0:
            return (value / 100) + 1.0
        else:
            return (100 / abs(value)) + 1.0
    return float(value)  # already decimal
```

---

## 8.4 Odds Change Detection

Only publish Kafka events if odds actually changed (avoids flooding):

```python
# sports_platform/ingestion/workers/odds_ingestion_worker.py

import hashlib
import json


def compute_odds_fingerprint(odds_list: list) -> str:
    """SHA-256 of sorted, stable odds representation."""
    sorted_odds = sorted(odds_list, key=lambda x: x["outcome"])
    canonical = json.dumps(sorted_odds, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class OddsIngestionWorker:
    def __init__(self, provider, producer, redis_client):
        self._provider = provider
        self._producer = producer
        self._redis = redis_client

    def ingest_odds_for_match(self, match_id: str, provider_match_id: str):
        odds_list = self._provider.fetch_match_odds(
            provider_match_id, markets=["match_winner", "over_under"]
        )

        for odds in odds_list:
            fingerprint = compute_odds_fingerprint(odds.outcomes)
            cache_key = f"odds:fp:{match_id}:{odds.market_type}:{self._provider.provider_name}"
            
            last_fingerprint = self._redis.get(cache_key)
            if last_fingerprint and last_fingerprint.decode() == fingerprint:
                continue  # Odds haven't changed, skip

            # Odds changed — publish to Kafka
            self._producer.publish_odds_updated(match_id, odds)
            self._redis.setex(cache_key, 3600, fingerprint)  # Cache fingerprint
```

---

## 8.5 Odds Data Model

### Redis (Current Odds - Fast Read)

```
match:odds:{match_id}:{market_type}
  provider:    "odds_provider_x"
  bookmaker:   "Bet365"
  home_win:    "1.85"
  away_win:    "2.10"
  draw:        "3.50"
  updated_at:  "1727781000"
  TTL: 4h

match:odds:history:{match_id}:{market_type}  (List, last 10 entries)
  ["1.90:2.05:3.40:1727770000", "1.87:2.08:3.45:1727775000", "1.85:2.10:3.50:1727781000"]
  TTL: 4h
```

### PostgreSQL (Durable)

```sql
-- Current state (upserted)
match_odds_current:
  match_id, provider_name, market_type, bookmaker, odds_data, is_open, updated_at

-- Historical (append-only)
match_odds_history:
  match_id, provider_name, market_type, bookmaker, odds_data, recorded_at
  UNIQUE(match_id, provider_name, market_type, recorded_at)
```

---

## 8.6 Odds in API Response

```json
// GET /api/matches/{id}
{
  "id": "match-uuid",
  "status": "live",
  "score": {...},
  "odds": {
    "match_winner": {
      "provider": "odds_provider_x",
      "bookmaker": "Bet365",
      "outcomes": [
        {"label": "home_win", "display": "RCB", "value": 1.85},
        {"label": "away_win", "display": "MI", "value": 2.10}
      ],
      "movement": [
        {"home_win": 1.90, "away_win": 2.05, "at": "2026-10-01T13:00:00Z"},
        {"home_win": 1.85, "away_win": 2.10, "at": "2026-10-01T14:00:00Z"}
      ],
      "updated_at": "2026-10-01T14:00:00Z"
    }
  },
  "odds_disclaimer": "Odds are for informational purposes only."
}
```

---

## 8.7 Odds History Endpoint

```
GET /api/matches/{id}/odds?market=match_winner&from=2026-10-01T12:00:00Z

Response:
{
  "match_id": "uuid",
  "market": "match_winner",
  "history": [
    {"outcomes": [...], "recorded_at": "2026-10-01T12:00:00Z"},
    {"outcomes": [...], "recorded_at": "2026-10-01T13:00:00Z"},
    {"outcomes": [...], "recorded_at": "2026-10-01T14:00:00Z"}
  ]
}
```

Source: PostgreSQL `match_odds_history` table (not Redis — history may exceed 10 entries).
