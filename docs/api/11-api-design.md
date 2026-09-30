# 11. API Design

## 11.1 API Conventions

- Base URL: `https://api.sports-platform.com/api/v1`
- Authentication: `Authorization: Bearer <jwt_access_token>`
- Pagination: `?page=1&page_size=20` (cursor-based for feeds)
- Error format: `{"error": {"code": "ERROR_CODE", "message": "...", "details": {}}}`
- All timestamps in ISO 8601 UTC format.
- `data_freshness_seconds`: included on live data responses to indicate staleness.

---

## 11.2 Authentication Endpoints

### POST /api/v1/auth/register

```json
// Request
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "Secure$Password123"
}

// Response 201
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "username": "johndoe"
  },
  "tokens": {
    "access": "eyJ...",
    "refresh": "eyJ..."
  }
}
```

### POST /api/v1/auth/login
```json
// Request
{"email": "user@example.com", "password": "Secure$Password123"}

// Response 200
{
  "tokens": {"access": "eyJ...", "refresh": "eyJ..."},
  "user": {"id": "uuid", "username": "johndoe"}
}
```

### POST /api/v1/auth/refresh
```json
// Request: {"refresh": "eyJ..."}
// Response: {"access": "eyJ..."}
```

### POST /api/v1/auth/logout
```json
// Request: {"refresh": "eyJ..."}
// Response: 204 No Content (token blacklisted)
```

---

## 11.3 User Preferences

### GET /api/v1/users/me/preferences

```json
// Response 200
{
  "sports": [
    {
      "sport": {"id": "uuid", "slug": "cricket", "name": "Cricket"},
      "following": {
        "teams": [
          {"id": "uuid", "name": "Royal Challengers Bengaluru", "logo_url": "https://..."}
        ],
        "competitions": [
          {"id": "uuid", "name": "Indian Premier League 2026"}
        ],
        "countries": [
          {"id": "uuid", "name": "India", "iso_code": "IND"}
        ],
        "players": [
          {"id": "uuid", "name": "Virat Kohli"}
        ]
      }
    },
    {
      "sport": {"id": "uuid", "slug": "football", "name": "Football"},
      "following": {
        "teams": [
          {"id": "uuid", "name": "Chelsea FC"},
          {"id": "uuid", "name": "Barcelona"}
        ],
        "competitions": [
          {"id": "uuid", "name": "Premier League 2025-26"}
        ],
        "countries": [],
        "players": []
      }
    }
  ],
  "max_sports": 3,
  "sports_remaining": 1
}
```

### PUT /api/v1/users/me/preferences

```json
// Request: Update entire preferences
{
  "sports": ["cricket", "football"],
  "following": [
    {"entity_type": "team", "entity_id": "uuid", "sport": "cricket"},
    {"entity_type": "competition", "entity_id": "uuid", "sport": "cricket"},
    {"entity_type": "team", "entity_id": "uuid", "sport": "football"}
  ]
}

// Response 200: updated preferences (same as GET response)
```

### POST /api/v1/users/me/preferences/follow
```json
// Request: Follow a single entity
{"entity_type": "team", "entity_id": "uuid", "sport": "cricket"}

// Response 201: {"message": "Following RCB in cricket"}

// Errors:
// 400: {"error": {"code": "MAX_SPORTS_REACHED", "message": "Maximum 3 sports allowed"}}
```

### DELETE /api/v1/users/me/preferences/follow/{entity_type}/{entity_id}
```
// Response 204 No Content
```

---

## 11.4 Feed

### GET /api/v1/feed

```json
// Query params: ?status=live,upcoming&cursor=...&page_size=20

// Response 200
{
  "matches": [
    {
      "id": "match-uuid",
      "sport": "cricket",
      "status": "live",
      "competition": {
        "id": "uuid",
        "name": "IPL 2026",
        "logo_url": "https://..."
      },
      "home_team": {
        "id": "uuid",
        "name": "Royal Challengers Bengaluru",
        "short_name": "RCB",
        "logo_url": "https://..."
      },
      "away_team": {
        "id": "uuid",
        "name": "Mumbai Indians",
        "short_name": "MI",
        "logo_url": "https://..."
      },
      "scheduled_at": "2026-10-01T14:00:00Z",
      "score": {
        "home": {"runs": 145, "wickets": 3, "overs": "15.2"},
        "away": {"runs": 0, "wickets": 0, "overs": "0.0"},
        "innings": 1
      },
      "last_event": {
        "type": "boundary",
        "description": "FOUR! Faf du Plessis drives through covers",
        "occurred_at": "2026-10-01T15:29:45Z"
      },
      "odds_summary": {
        "home_win": 1.85,
        "away_win": 2.10
      },
      "relevance_tags": ["team:RCB", "competition:IPL"],
      "data_freshness_seconds": 12
    }
  ],
  "pagination": {
    "next_cursor": "eyJ...",
    "has_more": true
  }
}
```

---

## 11.5 Matches

### GET /api/v1/matches/live

```json
// Query: ?sport=cricket&competition_id=uuid&page=1&page_size=20
// Response: same structure as feed, filtered to live matches
```

### GET /api/v1/matches/{id}

```json
// Response 200
{
  "id": "match-uuid",
  "sport": "cricket",
  "status": "live",
  "competition": {"id": "uuid", "name": "IPL 2026"},
  "home_team": {"id": "uuid", "name": "RCB", "logo_url": "..."},
  "away_team": {"id": "uuid", "name": "MI", "logo_url": "..."},
  "scheduled_at": "2026-10-01T14:00:00Z",
  "started_at": "2026-10-01T14:02:30Z",
  "venue": "M. Chinnaswamy Stadium, Bengaluru",
  "score": {
    "home": {"runs": 145, "wickets": 3, "overs": "15.2"},
    "away": {"runs": 0, "wickets": 0, "overs": "0.0"},
    "partnership": {"runs": 62, "balls": 38},
    "innings": 1,
    "sequence_number": 892
  },
  "odds": {
    "match_winner": {
      "outcomes": [
        {"label": "home_win", "display": "RCB", "value": 1.85},
        {"label": "away_win", "display": "MI", "value": 2.10}
      ],
      "updated_at": "2026-10-01T15:28:00Z"
    }
  },
  "data_freshness_seconds": 12,
  "odds_disclaimer": "Odds are for informational purposes only."
}
```

### GET /api/v1/matches/{id}/events

```json
// Query: ?since=2026-10-01T15:00:00Z&page=1&page_size=50
// Response 200
{
  "match_id": "uuid",
  "events": [
    {
      "id": "event-uuid",
      "type": "wicket",
      "sequence": 45,
      "over": "16.3",
      "description": "Kohli c Rohit b Bumrah 0 (1b)",
      "player": {"id": "uuid", "name": "Virat Kohli"},
      "bowler": {"id": "uuid", "name": "Jasprit Bumrah"},
      "score_after": {"runs": 145, "wickets": 4},
      "occurred_at": "2026-10-01T15:32:10Z"
    }
  ],
  "total": 45,
  "next_cursor": "eyJ..."
}
```

### GET /api/v1/matches/{id}/statistics

```json
// Response 200
{
  "match_id": "uuid",
  "period": "current",
  "teams": {
    "home": {
      "run_rate": 9.47,
      "boundaries": 14,
      "sixes": 6,
      "dot_balls": 28
    },
    "away": null  // Not batting yet
  },
  "updated_at": "2026-10-01T15:30:00Z"
}
```

### GET /api/v1/matches/{id}/odds

```json
// Query: ?market=match_winner
// Response 200
{
  "match_id": "uuid",
  "market": "match_winner",
  "current": {
    "outcomes": [
      {"label": "home_win", "display": "RCB", "value": 1.85},
      {"label": "away_win", "display": "MI", "value": 2.10}
    ],
    "bookmaker": "Bet365",
    "updated_at": "2026-10-01T15:28:00Z"
  },
  "history": [
    {"outcomes": [...], "recorded_at": "2026-10-01T13:00:00Z"},
    {"outcomes": [...], "recorded_at": "2026-10-01T14:00:00Z"},
    {"outcomes": [...], "recorded_at": "2026-10-01T15:28:00Z"}
  ],
  "disclaimer": "Odds are for informational purposes only."
}
```

---

## 11.6 AI Match Assistant

### POST /api/v1/ai/matches/{match_id}/ask

```json
// Request
{
  "question": "What's happening in this match? Why did the score drop so quickly?",
  "conversation_id": "uuid"  // optional; omit to start new conversation
}

// Response 200 (streamed via SSE or returned complete)
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "answer": "RCB are currently batting at 145/4 in 16.3 overs. The quick fall of wickets was triggered by Jasprit Bumrah's deadly spell — he took 2 wickets in his last over (16th over), including the prized scalp of Virat Kohli for a golden duck. Bumrah is known for his unplayable yorkers and deceptive pace variations, which are particularly effective in the death overs. RCB's middle order has historically struggled against quality pace bowling.",
  "sources": [
    {
      "title": "Jasprit Bumrah - Player Profile",
      "document_type": "player_profile",
      "relevance": 0.91
    }
  ],
  "data_used": ["live_score", "match_events"],
  "latency_ms": 2340
}
```

### GET /api/v1/ai/matches/{match_id}/conversations

```json
// Response 200
{
  "conversation_id": "uuid",
  "match_id": "uuid",
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "What's happening in this match?",
      "created_at": "2026-10-01T15:30:00Z"
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "RCB are currently batting...",
      "sources": [...],
      "created_at": "2026-10-01T15:30:02Z"
    }
  ]
}
```

---

## 11.7 Search / Discovery

### GET /api/v1/sports

```json
// Response: list of all active sports
{"sports": [{"id": "uuid", "slug": "cricket", "name": "Cricket"}, ...]}
```

### GET /api/v1/sports/{slug}/teams?q=chelsea&page=1

```json
// Response
{"teams": [{"id": "uuid", "name": "Chelsea FC", "country": "England", "logo_url": "..."}]}
```

### GET /api/v1/sports/{slug}/competitions?country=England

```json
// Response
{"competitions": [{"id": "uuid", "name": "Premier League 2025-26", ...}]}
```

---

## 11.8 WebSocket Connection

```
// Endpoint
wss://ws.sports-platform.com/ws/match/{match_id}?token={jwt_access_token}
wss://ws.sports-platform.com/ws/feed?token={jwt_access_token}

// On connect: server sends initial_state message
// Thereafter: server pushes score_updated, match_event, match_status_changed
// Client sends: {"type": "ping"} heartbeat every 30s
// Server sends: {"type": "pong"}
```

---

## 11.9 Notification Preferences

### GET /api/v1/users/me/notifications
### PUT /api/v1/users/me/notifications

```json
// Request
{
  "preferences": [
    {
      "sport": "cricket",
      "notification_type": "wicket",
      "is_enabled": true,
      "channels": {"websocket": true, "push": true}
    },
    {
      "sport": "football",
      "notification_type": "goal",
      "is_enabled": true,
      "channels": {"websocket": true, "push": false}
    }
  ]
}
```
