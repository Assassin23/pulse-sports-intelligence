# 4. Database Design (PostgreSQL)

## 4.1 Design Principles

- PostgreSQL is the **system of record** for all durable data.
- Redis holds the **current live state** only. Anything in Redis can be reconstructed from PostgreSQL.
- Use **UUIDs** as primary keys (v4) to avoid enumeration attacks and simplify distributed ID generation.
- All tables have `created_at` and `updated_at` timestamps.
- **Soft deletes** for user-owned data (`deleted_at` nullable timestamp).
- Indexes are designed for the specific query patterns described in the API design.

---

## 4.2 Schema

### 4.2.1 Users & Authentication

```sql
-- Core user table
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    username        VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    is_staff        BOOLEAN DEFAULT FALSE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users (email) WHERE deleted_at IS NULL;

-- JWT refresh token tracking (for revocation)
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 of token
    device_info     JSONB,
    ip_address      INET,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens (token_hash) WHERE revoked_at IS NULL;
```

---

### 4.2.2 Sports Reference Data

```sql
-- Sports catalog
CREATE TABLE sports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        VARCHAR(50) UNIQUE NOT NULL,  -- 'cricket', 'football', 'tennis'
    name        VARCHAR(100) NOT NULL,
    icon_url    VARCHAR(500),
    is_active   BOOLEAN DEFAULT TRUE
);

-- Countries
CREATE TABLE countries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    iso_code    VARCHAR(3) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL
);

-- Competitions / Leagues
CREATE TABLE competitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sport_id        UUID NOT NULL REFERENCES sports(id),
    country_id      UUID REFERENCES countries(id),  -- null for international
    name            VARCHAR(200) NOT NULL,
    short_name      VARCHAR(50),
    season          VARCHAR(20),  -- '2026', '2025-26'
    competition_type VARCHAR(50), -- 'league', 'cup', 'international'
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_competitions_sport ON competitions (sport_id);

-- Teams / Clubs
CREATE TABLE teams (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sport_id        UUID NOT NULL REFERENCES sports(id),
    country_id      UUID REFERENCES countries(id),
    name            VARCHAR(200) NOT NULL,
    short_name      VARCHAR(50),
    logo_url        VARCHAR(500),
    team_type       VARCHAR(20) DEFAULT 'club',  -- 'club', 'national'
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_teams_sport ON teams (sport_id);

-- Players
CREATE TABLE players (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sport_id        UUID NOT NULL REFERENCES sports(id),
    nationality_id  UUID REFERENCES countries(id),
    name            VARCHAR(200) NOT NULL,
    date_of_birth   DATE,
    position        VARCHAR(50),  -- sport-specific: 'batsman', 'bowler', 'forward', 'goalkeeper'
    photo_url       VARCHAR(500),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Provider ID mapping (decouples internal IDs from provider IDs)
CREATE TABLE provider_entity_mappings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_name       VARCHAR(50) NOT NULL,
    provider_entity_id  VARCHAR(200) NOT NULL,
    entity_type         VARCHAR(20) NOT NULL,  -- 'match', 'team', 'player', 'competition'
    internal_entity_id  UUID NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (provider_name, provider_entity_id, entity_type)
);

CREATE INDEX idx_provider_mappings_lookup 
    ON provider_entity_mappings (provider_name, entity_type, provider_entity_id);
```

---

### 4.2.3 User Preferences

```sql
-- Which sports a user follows (max 3)
CREATE TABLE user_sport_preferences (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sport_id    UUID NOT NULL REFERENCES sports(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, sport_id)
);

-- Enforce max 3 sports via application layer + DB check
CREATE INDEX idx_user_sport_prefs ON user_sport_preferences (user_id);

-- Followed entities (teams, competitions, countries, players)
CREATE TABLE user_followed_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sport_id        UUID NOT NULL REFERENCES sports(id),
    entity_type     VARCHAR(20) NOT NULL,  -- 'team', 'competition', 'country', 'player'
    entity_id       UUID NOT NULL,  -- references teams/competitions/countries/players
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, entity_type, entity_id)
);

CREATE INDEX idx_user_followed_user ON user_followed_entities (user_id);
CREATE INDEX idx_user_followed_entity ON user_followed_entities (entity_type, entity_id);

-- Notification preferences
CREATE TABLE user_notification_preferences (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sport_id            UUID NOT NULL REFERENCES sports(id),
    notification_type   VARCHAR(50) NOT NULL,  -- 'match_start', 'goal', 'wicket', 'red_card', 'match_end'
    is_enabled          BOOLEAN DEFAULT TRUE,
    channel_websocket   BOOLEAN DEFAULT TRUE,
    channel_push        BOOLEAN DEFAULT TRUE,
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, sport_id, notification_type)
);
```

---

### 4.2.4 Matches

```sql
CREATE TYPE match_status AS ENUM (
    'scheduled', 'live', 'half_time', 'paused', 'completed', 'postponed', 'cancelled', 'abandoned'
);

CREATE TABLE matches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sport_id        UUID NOT NULL REFERENCES sports(id),
    competition_id  UUID NOT NULL REFERENCES competitions(id),
    home_team_id    UUID NOT NULL REFERENCES teams(id),
    away_team_id    UUID NOT NULL REFERENCES teams(id),
    scheduled_at    TIMESTAMPTZ NOT NULL,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    status          match_status DEFAULT 'scheduled',
    venue           VARCHAR(300),
    round           VARCHAR(50),
    metadata        JSONB DEFAULT '{}',  -- sport-specific extra data
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Primary query patterns
CREATE INDEX idx_matches_scheduled ON matches (scheduled_at) WHERE status = 'scheduled';
CREATE INDEX idx_matches_live ON matches (status) WHERE status = 'live';
CREATE INDEX idx_matches_competition ON matches (competition_id, scheduled_at DESC);
CREATE INDEX idx_matches_team ON matches (home_team_id, scheduled_at DESC);
CREATE INDEX idx_matches_away_team ON matches (away_team_id, scheduled_at DESC);
CREATE INDEX idx_matches_updated ON matches (updated_at DESC) WHERE status = 'live';

-- Current match score (denormalized for fast access; Redis is authoritative when live)
CREATE TABLE match_scores (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id    UUID UNIQUE NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    score_data  JSONB NOT NULL DEFAULT '{}',  -- sport-specific, flexible
    sequence_number BIGINT DEFAULT 0,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Match events (goals, wickets, red cards, etc.)
CREATE TABLE match_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id        UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    sport_id        UUID NOT NULL REFERENCES sports(id),
    event_type      VARCHAR(50) NOT NULL,  -- 'goal', 'wicket', 'red_card', 'yellow_card', etc.
    event_sequence  INTEGER NOT NULL,       -- ordering within match
    occurred_at     TIMESTAMPTZ,
    minute          INTEGER,                -- football: match minute
    over_ball       VARCHAR(10),            -- cricket: '16.3'
    player_id       UUID REFERENCES players(id),
    secondary_player_id UUID REFERENCES players(id),  -- bowler, assister, etc.
    team_id         UUID REFERENCES teams(id),
    description     TEXT,
    event_data      JSONB DEFAULT '{}',    -- sport-specific extra fields
    source_provider VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (match_id, source_provider, event_sequence)
);

CREATE INDEX idx_match_events_match ON match_events (match_id, event_sequence);
CREATE INDEX idx_match_events_type ON match_events (match_id, event_type);
CREATE INDEX idx_match_events_player ON match_events (player_id) WHERE player_id IS NOT NULL;

-- Match statistics snapshots
CREATE TABLE match_statistics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id    UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id     UUID NOT NULL REFERENCES teams(id),
    stat_type   VARCHAR(50) NOT NULL,  -- 'possession', 'shots', 'run_rate', etc.
    value       NUMERIC,
    value_json  JSONB,  -- for complex stats
    period      VARCHAR(20),  -- 'first_half', 'second_half', 'full', 'innings_1', etc.
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_match_stats_match ON match_statistics (match_id, team_id);
```

---

### 4.2.5 Odds

```sql
-- Normalized odds (single record per match+market, updated in place for current state)
CREATE TABLE match_odds_current (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id        UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    provider_name   VARCHAR(100) NOT NULL,
    market_type     VARCHAR(50) NOT NULL,  -- 'match_winner', 'handicap', 'over_under'
    bookmaker       VARCHAR(100),
    odds_data       JSONB NOT NULL,        -- [{"outcome":"home_win","value":1.85}, ...]
    is_open         BOOLEAN DEFAULT TRUE,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (match_id, provider_name, market_type)
);

CREATE INDEX idx_odds_match ON match_odds_current (match_id);

-- Odds history (append-only, never updated)
CREATE TABLE match_odds_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id        UUID NOT NULL REFERENCES matches(id),
    provider_name   VARCHAR(100) NOT NULL,
    market_type     VARCHAR(50) NOT NULL,
    bookmaker       VARCHAR(100),
    odds_data       JSONB NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    UNIQUE (match_id, provider_name, market_type, recorded_at)
);

CREATE INDEX idx_odds_history_match ON match_odds_history (match_id, market_type, recorded_at DESC);
```

---

### 4.2.6 AI & Conversations

```sql
-- AI conversation sessions (one per user per match)
CREATE TABLE ai_conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_id    UUID NOT NULL REFERENCES matches(id),
    title       VARCHAR(300),  -- auto-generated from first question
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, match_id)
);

CREATE INDEX idx_conversations_user ON ai_conversations (user_id, updated_at DESC);

-- Individual messages in a conversation
CREATE TABLE ai_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,  -- 'user', 'assistant', 'tool'
    content         TEXT NOT NULL,
    tool_calls      JSONB,  -- LangGraph tool call metadata
    tool_results    JSONB,  -- tool return values for audit/replay
    sources         JSONB,  -- RAG citations
    token_usage     JSONB,  -- {input_tokens, output_tokens, model}
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_messages_conversation ON ai_messages (conversation_id, created_at);
```

---

### 4.2.7 RAG Documents

```sql
-- Document registry for the RAG system
CREATE TABLE rag_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    source_url      VARCHAR(1000),
    document_type   VARCHAR(50) NOT NULL,  -- 'team_profile', 'player_profile', 'competition_rules', 'article', 'terminology'
    sport_id        UUID REFERENCES sports(id),
    entity_type     VARCHAR(20),   -- 'team', 'player', 'competition', 'general'
    entity_id       UUID,          -- references the entity if applicable
    content_hash    VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256, for dedup
    raw_content     TEXT,          -- kept for re-chunking if needed
    language        VARCHAR(10) DEFAULT 'en',
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE
);

-- Chunks derived from documents
CREATE TABLE rag_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER,
    embedding       vector(1536),  -- pgvector; OpenAI text-embedding-3-small dimension
    metadata        JSONB DEFAULT '{}',  -- {sport, entity_type, entity_id, title, published_at}
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

-- HNSW index for ANN search
CREATE INDEX idx_rag_chunks_embedding 
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Filter index for metadata queries
CREATE INDEX idx_rag_chunks_metadata ON rag_chunks USING gin (metadata);
```

---

### 4.2.8 Notifications

```sql
-- Sent notification log
CREATE TABLE notification_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_id            UUID REFERENCES matches(id),
    notification_type   VARCHAR(50) NOT NULL,
    title               VARCHAR(300) NOT NULL,
    body                TEXT NOT NULL,
    channel             VARCHAR(20) NOT NULL,  -- 'websocket', 'push'
    status              VARCHAR(20) DEFAULT 'sent',  -- 'sent', 'delivered', 'failed'
    sent_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notification_log (user_id, sent_at DESC);
```

---

## 4.3 Key Constraints Summary

| Rule | Enforcement |
|---|---|
| Max 3 sports per user | Application layer + pre-save check |
| Unique match per provider | `UNIQUE (provider_name, provider_entity_id)` in mappings |
| Unique match event per provider sequence | `UNIQUE (match_id, source_provider, event_sequence)` |
| Unique odds history snapshot | `UNIQUE (match_id, provider_name, market_type, recorded_at)` |
| RAG document dedup | `UNIQUE content_hash` |
| Soft delete users | `deleted_at IS NULL` in all user queries |

---

## 4.4 Partitioning Strategy (Future)

When `match_events` exceeds 50M rows (at scale), partition by `created_at` monthly:

```sql
-- Future: range partition match_events by month
CREATE TABLE match_events_2026_10 PARTITION OF match_events
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
```

`match_odds_history` similarly partitioned monthly when it grows.
