# Milestone 7 & 8 Architecture: Odds Ingestion, Notifications & Tri-Match Tactical Console

## 1. Overview
This release implements **Milestone 7 (Odds Ingestion)** and **Milestone 8 (Notifications & User Console Session)**, paired with a complete visual and architectural redesign of the Pulse Dashboard: the **Tri-Match Tactical Command Console & Ambient Perimeter Radar**.

---

## 2. Milestone 7: Odds Ingestion & Normalization

### 2.1 Regulatory & Compliance Principles
- **Informational and Analytical Only**: No betting, wagering, or financial transaction capabilities.
- **Mandatory Disclaimer**: All API responses and UI displays contain:
  > *"Odds are for informational and statistical analysis only. No betting or wagering capabilities."*

### 2.2 Normalization & Change Fingerprinting
- **Module**: `sports_platform/providers/odds_normalization.py`
  - Maps external markets (`1X2`, `Full Time Result`, `Moneyline`, `OU`, `BTTS`) to canonical identifiers (`match_winner`, `over_under`, `both_teams_to_score`).
  - Normalizes odds values into standard decimal format rounded to 2 decimal places.
  - Computes deterministic SHA-256 fingerprints to ensure unchanged odds updates are ignored.

### 2.3 Storage Architecture
- **PostgreSQL Durable Models** (`sports_platform/matches/models.py`):
  - `MatchOddsCurrent`: Upserted snapshot of current market prices per bookmaker (`Bet365`, `Pinnacle`, `Betfair`).
  - `MatchOddsHistory`: Append-only historical price movements for time-series charts.
- **Redis Cache & PubSub** (`sports_platform/matches/redis_store.py`):
  - `match:odds:{match_id}:{market_type}`: Hash containing current outcomes, line movement, and bookmaker.
  - `match:odds:history:{match_id}:{market_type}`: List of last 10 price movement points.
  - Publishes `odds_updated` payload to `ws:match:{match_id}` for real-time frontend streaming.

### 2.4 API Endpoints
- `GET /api/v1/matches/{id}/odds/?market=match_winner`: Current odds and historical price movements.
- `GET /api/v1/matches/{id}/`: Includes current `odds` snapshot and `odds_disclaimer`.
- `GET /api/v1/matches/live/`: Enriches live matches with real-time odds when available.

---

## 3. Milestone 8: Notifications & Background Radar

### 3.1 Architecture & Fanout Service
- **Module**: `sports_platform/notifications/fanout.py`
  - Targets users following match entities (`home_team`, `away_team`, `competition`).
  - Evaluates `UserNotificationPreference` per event type (`goal`, `wicket`, `red_card`, `match_start`).
  - Applies per-user, per-match rate limiting (max 3 notifications/type/match/5min).
  - Cross-references `UserConsoleSession`: tags alerts as `is_background: true` when events occur in matches outside the user's active 3-slot console.

### 3.2 Notification Models & Endpoints
- `NotificationLog` (`sports_platform/preferences/models.py`): Durable audit log of sent notifications.
- `GET /api/v1/users/me/notifications/`: List notifications with `unread_count`.
- `POST /api/v1/users/me/notifications/{id}/read/`: Mark single notification as read.
- `POST /api/v1/users/me/notifications/mark-all-read/`: Mark all notifications as read.
- `POST /api/v1/users/me/notifications/test-event/`: Simulates a background match event for immediate verification.

---

## 4. User Console Session & Tri-Match Tactical Orbit UI

### 4.1 Backend Console State
- `UserConsoleSession` (`sports_platform/preferences/models.py`):
  - Persists `pinned_matches` (up to 3 match UUIDs).
  - Persists `active_match_id`, `console_mode` (`circular` vs `triangular`), and `rotation_angle`.
- Endpoints:
  - `GET /api/v1/users/me/console/`: Fetches user's 3-match command console state (auto-initializes if empty).
  - `PUT /api/v1/users/me/console/`: Saves pinned matches and rotation state across sessions.

### 4.2 Frontend UX Redesign (`pulse-FE/src/components/pulse-dashboard.tsx`)
1. **Tri-Match Tactical Orbit (Centerpiece)**:
   - Max 3 live matches pinned to **Slot 1**, **Slot 2**, and **Slot 3**.
   - Rotary selector with smooth ↺ Left and ↻ Right rotation controls, or direct slot click.
   - Dual geometry modes: **Circular Dial** vs **Triangular Hub**.
   - Hero Active Match View:
     - High-fidelity live scoreboard with team crests and real-time pulse badges.
     - **Live Odds Tab (M7)**: Bookmaker comparison (`Bet365`, `Pinnacle`, `Betfair`), implied probability gauges, and line movement trends with mandatory compliance disclaimer.
     - **Timeline Tab**: Chronological match events with dynamic icons.
     - **Tactical Stats Tab**: Momentum and territory gauges.
   - Flanking Peripheral Slots: Shows compact cards for the other 2 pinned matches with 1-click rotation into the center.
2. **Ambient Live Perimeter Radar**:
   - Clean background deck showcasing matches not currently inside the 3-match console.
   - Filter by sport (`All`, `Football`, `Cricket`, `Tennis`).
   - Drag & drop or 1-click "Pin to Console" to promote any background match.
3. **Background Event Notification Radar**:
   - Glowing banner appears whenever a goal/wicket/red card occurs in a background match.
   - Provides a 1-click `[ Swap into Main Console ]` action.
   - Notification Drawer with test simulation trigger (`Test Radar Alert`).
