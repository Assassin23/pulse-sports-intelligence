# Milestone 6 Post-Processing: Hierarchical Preferences & Multi-Sport Entity Taxonomy

## 1. Executive Summary & Objectives

### 1.1 Context & Strategic Placement
Before completing and deploying **Milestones 6–8** (WebSocket Live Updates, Odds Ingestion, and Notification Fanout), the **Preferences System** and **Sports Reference Taxonomy** require a dedicated architectural overhaul.

In Milestones 6 through 8:
- **WebSocket Gateway (M6)** routes live match events to personal channels based on followed entities.
- **Odds Ingestion (M7)** prioritizes matches involving user-favorited teams and tournaments.
- **Notification Fanout (M8)** filters and dispatches push alerts when followed clubs, national sides, or tournaments trigger key events (goals, wickets, sets).

If user preferences remain flat and unorganized, the downstream intelligence and notification layers lack the semantic fidelity needed to personalize the platform effectively.

### 1.2 Core Scope & Focus
For this post-processing milestone, we focus on the **three foundational sports**:
1. **Football (Soccer)**: Tiered team sport (Club competitions vs. International national tournaments).
2. **Cricket**: Multi-format team sport (Franchise leagues like IPL vs. International bilateral & ICC World Cups).
3. **Tennis**: Individual athlete & tournament sport (Grand Slams, ATP/WTA Tours, ranked singles/doubles athletes).

---

## 2. Requirements & UX Gap Analysis

### 2.1 Current State Limitations
1. **Flat Entity Lists**: The existing preferences screen renders all teams and competitions in an unstructured, alphabetical list with basic string searching.
2. **Missing Relational Hierarchy**: Competitions and Teams are disconnected in the database. When a user selects a league (e.g., *Premier League* or *IPL*), the platform cannot fetch or display the teams competing within that league.
3. **No Club vs. Country Classification**: Football and Cricket fans support clubs (e.g., *Manchester United*, *Chennai Super Kings*) and national teams (e.g., *England*, *India*) differently. There is currently no UI distinction between club and international teams.
4. **Mismatched UX for Individual Sports**: Tennis does not fit the "Club vs. Country" paradigm. Forcing Tennis into a team layout produces empty states and user confusion. Tennis fans want to follow **Tournaments** (Grand Slams) and **Individual Players** (ATP/WTA stars).

### 2.2 Functional Requirements

#### A. Team Sports Flow (Football & Cricket)
- **Step 1: Select Sport**: Select Football or Cricket (enforcing the strict **Max 3 Sports** rule).
- **Step 2: Dual Exploration Modes**:
  - **Mode 1: Browse by Competition / League (Drill-Down)**:
    - User selects a competition (e.g., *Premier League*, *UEFA Champions League*, *IPL*, *ICC Men's T20 World Cup*).
    - 1-click option to follow the competition itself.
    - System dynamically queries and displays the **participating teams in that league**.
    - User can follow/unfollow individual teams directly within the league roster.
  - **Mode 2: Browse by Team Type (Classification Filter)**:
    - Segmented filter: `[All Teams]` | `[Clubs / Franchises]` | `[National Teams]`.
    - Instant search across teams with country badge and league affiliation.
- **Step 3: Direct Follow Actions**: Instant optimistic follow/unfollow toggles with Sonner toast feedback and backend persistence.

#### B. Individual Sport Flow (Tennis)
- **Automatic Sport Adaptation**: Selecting Tennis dynamically shifts the UI into a specialized two-tier layout:
  - **Tier 1: Tournaments & Grand Slams**: Wimbledon, Roland Garros, US Open, Australian Open, ATP Masters 1000, WTA Tour.
  - **Tier 2: Star Players & Athletes**: Top ATP & WTA singles champions (e.g., Carlos Alcaraz, Jannik Sinner, Novak Djokovic, Iga Swiatek, Aryna Sabalenka), complete with nationality flag, ranking/seed, and follow toggle.

#### C. Preferences Summary & Persistence
- Persistent bottom/top summary ribbon displaying:
  - Total Sports Followed (`X / 3`).
  - Breakdown: Followed Competitions (`N`), Clubs (`M`), National Teams (`K`), Tennis Players (`P`).
  - Seamless background synchronization with rollback on network failure.

---

## 3. Data Model & Database Architecture

### 3.1 Entity Relationship Diagram

```text
  ┌────────────────────────────────────────────────────────┐
  │                         Sport                          │
  │  (slug: 'football' | 'cricket' | 'tennis')             │
  └───────────────┬────────────────────────┬───────────────┘
                  │ 1:N                    │ 1:N
                  ▼                        ▼
     ┌────────────────────────┐       ┌────────────────────────┐
     │      Competition       │       │          Team          │
     │ - league               │       │ - name                 │
     │ - cup                  │       │ - short_name           │
     │ - international        │       │ - team_type ('club'    │
     │ - grand_slam           │       │    | 'national')       │
     └────────────┬───────────┘       └────────────┬───────────┘
                  │                                │
                  │     ┌────────────────────┐     │
                  └────►│  CompetitionTeam   │◄────┘
                        │ (M2M through table)│
                        │ - season ('2025-26')│
                        │ - is_active        │
                        └────────────────────┘

  ┌────────────────────────────────────────────────────────┐
  │                 User Preferences                      │
  ├────────────────────────────────────────────────────────┤
  │ UserSportPreference     : (user_id, sport_id) [Max 3]  │
  │ UserFollowedEntity      : (user_id, entity_type,       │
  │                           entity_id, sport_id)         │
  │                           entity_type: team |          │
  │                                        competition |   │
  │                                        player |        │
  │                                        country         │
  └────────────────────────────────────────────────────────┘
```

### 3.2 Django Schema Enhancement (`sports_platform/sports/models.py`)

To support dynamic league rosters without coupling to match schedules, we introduce the `CompetitionTeam` through-model:

```python
class CompetitionTeam(models.Model):
    """
    Associates a team with a competition for a specific season/campaign.
    Enables instant lookup of all teams participating in a tournament or league.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    competition = models.ForeignKey(
        "sports.Competition",
        on_delete=models.CASCADE,
        related_name="competition_teams"
    )
    team = models.ForeignKey(
        "sports.Team",
        on_delete=models.CASCADE,
        related_name="team_competitions"
    )
    season = models.CharField(max_length=20, default="2025-26", blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "competition_teams"
        unique_together = [("competition", "team", "season")]
        indexes = [
            models.Index(fields=["competition", "is_active"], name="idx_comp_teams_lookup"),
            models.Index(fields=["team", "is_active"], name="idx_team_comps_lookup"),
        ]

    def __str__(self) -> str:
        return f"{self.team.name} in {self.competition.name} ({self.season})"
```

---

## 4. Reference Data Seeding Blueprint

The `seed_sports` command (`sports_platform/sports/management/commands/seed_sports.py`) will be updated to populate high-fidelity reference datasets across all three sports:

### 4.1 Football (Soccer)
* **Competitions**:
  - `Premier League` (Type: `league`, Country: `GBR`, Season: `2025-26`)
  - `La Liga` (Type: `league`, Country: `ESP`, Season: `2025-26`)
  - `UEFA Champions League` (Type: `cup`, Country: `None`, Season: `2025-26`)
  - `FIFA World Cup` (Type: `international`, Country: `None`, Season: `2026`)
* **Clubs**:
  - Premier League clubs: Arsenal, Chelsea, Liverpool, Manchester City, Manchester United, Tottenham Hotspur, Aston Villa, Newcastle United.
  - La Liga clubs: Real Madrid, FC Barcelona, Atletico Madrid.
  - European clubs: Bayern Munich, Paris Saint-Germain, Inter Milan.
* **National Teams**:
  - England, Spain, France, Germany, Brazil, Argentina, Portugal.
* **Linkages (`CompetitionTeam`)**:
  - Premier League: Links all 8 English clubs.
  - Champions League: Links top European clubs (Real Madrid, Man City, Bayern, PSG, Arsenal, Barca).
  - FIFA World Cup: Links all National Teams.

### 4.2 Cricket
* **Competitions**:
  - `Indian Premier League` (Type: `league`, Country: `IND`, Season: `2026`)
  - `Big Bash League` (Type: `league`, Country: `AUS`, Season: `2025-26`)
  - `ICC Men's T20 World Cup` (Type: `international`, Country: `None`, Season: `2026`)
  - `ICC World Test Championship` (Type: `international`, Country: `None`, Season: `2025-27`)
* **Franchise Teams (Clubs)**:
  - IPL: Royal Challengers Bengaluru (RCB), Chennai Super Kings (CSK), Mumbai Indians (MI), Kolkata Knight Riders (KKR), Rajasthan Royals (RR), Sunrisers Hyderabad (SRH), Gujarat Titans (GT), Delhi Capitals (DC).
* **National Teams**:
  - India, Australia, England, South Africa, New Zealand, Pakistan.
* **Linkages (`CompetitionTeam`)**:
  - IPL: Links all 8 IPL franchise teams.
  - ICC Men's T20 World Cup: Links all 6 National Cricket Teams.

### 4.3 Tennis
* **Tournaments (Competitions)**:
  - `Wimbledon` (Type: `grand_slam`, Country: `GBR`, Season: `2026`)
  - `Roland Garros` (Type: `grand_slam`, Country: `FRA`, Season: `2026`)
  - `US Open` (Type: `grand_slam`, Country: `USA`, Season: `2026`)
  - `Australian Open` (Type: `grand_slam`, Country: `AUS`, Season: `2026`)
  - `ATP Finals` (Type: `cup`, Country: `ITA`, Season: `2026`)
  - `Indian Wells Masters` (Type: `league`, Country: `USA`, Season: `2026`)
* **Athletes (Players)**:
  - ATP Men's Singles: Carlos Alcaraz (ESP), Jannik Sinner (ITA), Novak Djokovic (SRB), Daniil Medvedev, Alexander Zverev (GER).
  - WTA Women's Singles: Iga Swiatek (POL), Aryna Sabalenka, Coco Gauff (USA), Elena Rybakina (KAZ).

---

## 5. Backend REST API Specifications

### 5.1 Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/sports/` | List all available sports with active flag | No |
| `GET` | `/api/v1/sports/{slug}/competitions/` | List competitions for sport (supports `?type=league\|cup\|international`) | No |
| `GET` | `/api/v1/sports/{slug}/competitions/{id}/teams/` | **NEW:** Fetch all teams participating in a competition | No |
| `GET` | `/api/v1/sports/{slug}/teams/` | Search teams in sport (supports `?type=club\|national` & `?competition_id=`) | No |
| `GET` | `/api/v1/sports/{slug}/players/` | List/search players in sport (Tennis athletes) | No |
| `GET` | `/api/v1/users/me/preferences/` | Get current user's followed sports, teams, competitions, players | Yes |
| `POST` | `/api/v1/users/me/preferences/follow/` | Follow an entity (`sport`, `entity_type`, `entity_id`) | Yes |
| `DELETE` | `/api/v1/users/me/preferences/follow/{type}/{id}/` | Unfollow an entity | Yes |

### 5.2 Competition Teams Response Schema (`GET /api/v1/sports/{slug}/competitions/{id}/teams/`)

```json
{
  "competition": {
    "id": "c8b4f169-d41c-4b68-98e3-a4c330df32d0",
    "name": "Premier League",
    "short_name": "EPL",
    "season": "2025-26",
    "competition_type": "league",
    "country": {
      "iso_code": "GBR",
      "name": "United Kingdom"
    }
  },
  "teams": [
    {
      "id": "e2f12c19-74e2-47d0-a029-45bcde1f32a1",
      "name": "Arsenal",
      "short_name": "ARS",
      "team_type": "club",
      "logo_url": "https://cdn.example.com/teams/arsenal.png",
      "country": { "iso_code": "GBR", "name": "United Kingdom" }
    },
    {
      "id": "993a4b60-8451-4099-9238-bdcf17398188",
      "name": "Manchester City",
      "short_name": "MCI",
      "team_type": "club",
      "logo_url": "https://cdn.example.com/teams/mancity.png",
      "country": { "iso_code": "GBR", "name": "United Kingdom" }
    }
  ],
  "count": 20
}
```

---

## 6. Frontend UI/UX Architecture (`pulse-FE`)

### 6.1 Component Hierarchy

```text
src/
└── components/
    ├── profile-screen.tsx                # Main container tab shell
    └── preferences/
        ├── PreferencesWorkspace.tsx      # Main state container & orchestrator
        ├── SportSelectorRibbon.tsx       # 3-Sport ribbon with Max 3 validation
        ├── TeamSportPreferences.tsx      # Dual-mode viewer for Football & Cricket
        │   ├── CompetitionLeagueSelector.tsx  # League carousel/selector
        │   ├── CompetitionTeamsGrid.tsx       # Dynamic roster of selected league
        │   └── TeamTypeClassificationView.tsx # Club vs. National segmented tab
        ├── TennisPreferences.tsx         # Specialized Tennis layout (Tournaments + Players)
        │   ├── TennisTournamentsGrid.tsx      # Grand Slams & Masters
        │   └── TennisPlayersGrid.tsx          # Star ATP/WTA athletes
        └── PreferencesSummaryBar.tsx     # Followed count badges & sync status
```

### 6.2 UI Wireframes & Layout Flow

#### A. Main Ribbon & Sport Selector
```text
+-----------------------------------------------------------------------------------------+
|  YOUR FOLLOWED SPORTS  [ 2 / 3 Selected ]                          [ Autosave: Synced ] |
|                                                                                         |
|  [ ✓ Football ]               [ ✓ Cricket ]                 [ + Tennis ]                |
|    Active Inspector              Switch View                   Click to Add             |
+-----------------------------------------------------------------------------------------+
```

#### B. Football / Cricket Workspace: Mode 1 (By Competition Drill-Down)
```text
+-----------------------------------------------------------------------------------------+
|  FOOTBALL PREFERENCES                                                                   |
|  View Mode:  (●) By Competition / League      ( ) By Team Type (Club vs National)       |
|                                                                                         |
|  Select League:                                                                         |
|  [ ★ Premier League (20) ]  [ Champions League (32) ]  [ La Liga (20) ]  [ World Cup ]  |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | Premier League · 2025-26 Season                           [ ★ Follow Entire League]|  |
|  | 20 Teams in this competition:                                                     |  |
|  |                                                                                   |  |
|  |  +---------------------+   +---------------------+   +---------------------+      |  |
|  |  | [ARS] Arsenal       |   | [MCI] Man City      |   | [LIV] Liverpool     |      |  |
|  |  | Club · London       |   | Club · Manchester   |   | Club · Liverpool    |      |  |
|  |  | [ ✓ Followed ]      |   | [ + Follow ]        |   | [ + Follow ]        |      |  |
|  |  +---------------------+   +---------------------+   +---------------------+      |  |
|  |  +---------------------+   +---------------------+   +---------------------+      |  |
|  |  | [CHE] Chelsea       |   | [MUN] Man United    |   | [TOT] Tottenham     |      |  |
|  |  | Club · London       |   | Club · Manchester   |   | Club · London       |      |  |
|  |  | [ + Follow ]        |   | [ ✓ Followed ]      |   | [ + Follow ]        |      |  |
|  |  +---------------------+   +---------------------+   +---------------------+      |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

#### C. Football / Cricket Workspace: Mode 2 (By Team Type Filter)
```text
+-----------------------------------------------------------------------------------------+
|  FOOTBALL PREFERENCES                                                                   |
|  View Mode:  ( ) By Competition / League      (●) By Team Type                          |
|                                                                                         |
|  Team Category:  [ All Teams (25) ]   [ ★ Clubs (18) ]   [ National Teams (7) ]         |
|  Search Teams:   [ Search club or country...                                 🔍 ]       |
|                                                                                         |
|  +---------------------+   +---------------------+   +---------------------+            |
|  | [ENG] England       |   | [FRA] France        |   | [ESP] Spain         |            |
|  | National Team       |   | National Team       |   | National Team       |            |
|  | [ ✓ Followed ]      |   | [ + Follow ]        |   | [ + Follow ]        |            |
|  +---------------------+   +---------------------+   +---------------------+            |
+-----------------------------------------------------------------------------------------+
```

#### D. Tennis Workspace (Specialized Individual Sport Flow)
```text
+-----------------------------------------------------------------------------------------+
|  TENNIS PREFERENCES                                                                     |
|  View Mode:  [ Tournaments & Grand Slams ]       [ Star Players & Athletes ]            |
|                                                                                         |
|  GRAND SLAMS & TOURS                                                                    |
|  +---------------------+   +---------------------+   +---------------------+            |
|  | [🎾] Wimbledon      |   | [🎾] Roland Garros  |   | [🎾] US Open        |            |
|  | Grand Slam · GBR    |   | Grand Slam · FRA    |   | Grand Slam · USA    |            |
|  | [ ✓ Followed ]      |   | [ + Follow ]        |   | [ + Follow ]        |            |
|  +---------------------+   +---------------------+   +---------------------+            |
|                                                                                         |
|  TOP RANKED PLAYERS                                                                     |
|  +---------------------+   +---------------------+   +---------------------+            |
|  | [🇪🇸] Carlos Alcaraz |   | [🇮🇹] Jannik Sinner  |   | [🇵🇱] Iga Swiatek    |            |
|  | ATP #1 · Spain      |   | ATP #2 · Italy      |   | WTA #1 · Poland     |            |
|  | [ ✓ Followed ]      |   | [ + Follow ]        |   | [ ✓ Followed ]      |            |
|  +---------------------+   +---------------------+   +---------------------+            |
+-----------------------------------------------------------------------------------------+
```

---

## 7. Phased Implementation Plan

### Phase 1: Database Migration & Model Definition
* **Goal**: Create the `CompetitionTeam` through-model and establish relational indexes.
* **Tasks**:
  1. Add `CompetitionTeam` to `sports_platform/sports/models.py`.
  2. Create and apply Django migration `0002_competition_teams.py`.
  3. Register `CompetitionTeam` in Django Admin (`sports_platform/sports/admin.py`) for management visibility.

### Phase 2: Reference Data Seed Pipeline
* **Goal**: Populate rich, accurate data for Football, Cricket, and Tennis.
* **Tasks**:
  1. Update `sports_platform/sports/management/commands/seed_sports.py`.
  2. Seed the 20 Premier League clubs, Spanish clubs, and major European clubs.
  3. Seed Football National Teams (England, Spain, France, Germany, Brazil, Argentina).
  4. Seed 10 IPL franchise teams and Cricket National Teams (India, Australia, England, South Africa).
  5. Seed the 4 Grand Slam tournaments, ATP Masters, and top 10 ATP/WTA tennis players.
  6. Execute `python manage.py seed_sports` to build canonical relations.

### Phase 3: Backend API Views & URL Routing
* **Goal**: Provide high-performance query endpoints for hierarchical fetching.
* **Tasks**:
  1. Implement `CompetitionTeamListView` in `sports_platform/sports/views.py`:
     - Path: `GET /api/v1/sports/<slug>/competitions/<id>/teams/`
     - Caching: 1-hour Redis TTL on team rosters (`comp:teams:<id>`).
  2. Enhance `TeamListView` in `sports_platform/sports/views.py` with `competition_id` query param.
  3. Add unit and integration tests in `tests/unit/test_sports_reference.py`.

### Phase 4: Frontend API Client & TypeScript Interfaces
* **Goal**: Update `pulse-FE` client with typed methods for competition teams.
* **Tasks**:
  1. Add `CompetitionTeamsResponse` interface to `src/lib/api.ts`.
  2. Add `api.sports.getCompetitionTeams(sportSlug, competitionId)` client method.
  3. Update `api.sports.getTeams(sportSlug, { type, competitionId, q })` to accept typed query filters.

### Phase 5: Frontend UI Redesign & Component Engineering
* **Goal**: Build the responsive, sport-aware preferences workspace.
* **Tasks**:
  1. Create modular components in `src/components/preferences/`.
  2. Implement `SportSelectorRibbon` with visual count badge and 3-sport limit guard.
  3. Build `TeamSportPreferences` supporting "By Competition Drill-Down" and "Club vs National" views.
  4. Build `TennisPreferences` supporting Grand Slam tournaments and ATP/WTA player cards.
  5. Integrate `PreferencesSummaryBar` with optimistic follow/unfollow states.
  6. Integrate newly structured workspace into `src/components/profile-screen.tsx`.

### Phase 6: End-to-End Verification & QA
* **Goal**: Validate end-to-end user journeys across all three sports.
* **Tasks**:
  1. Verify Max 3 sports rule prevents selecting 4th sport.
  2. Verify selecting *Premier League* immediately fetches and renders Arsenal, Man City, etc.
  3. Verify toggling *Club* vs. *National* displays distinct team rosters.
  4. Verify Tennis renders Grand Slams and Tennis players rather than empty team tables.
  5. Verify followed entities persist across page refresh and reflect in personal feed (`/api/v1/feed/`).

---

## 8. Impact on Subsequent Milestones

```text
  +-----------------------------------------------------------+
  |        Milestone 6 Post-Processing (Hierarchical Prefs)   |
  |  - Club vs. National taxonomy                             |
  |  - Competition -> Teams mapping                           |
  |  - Tennis Tournament & Player entity tracking             |
  +-----------------------------┬-----------------------------+
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
+───────────────+       +───────────────+       +───────────────+
|  Milestone 6  |       |  Milestone 7  |       |  Milestone 8  |
|  WebSocket    |       |  Odds Engine  |       | Notifications |
|  - Subscribes |       |  - Fetches    |       | - Dispatches  |
|    to user-   |       |    odds for   |       |    alerts for |
|    followed   |       |    followed   |       |    followed   |
|    clubs and  |       |    clubs and  |       |    teams vs   |
|    leagues    |       |    tournaments|       |    leagues    |
+───────────────+       +───────────────+       +───────────────+
```

1. **Milestone 6 (WebSocket Live Updates)**:
   - When a user joins `ws://gateway/ws/feed`, the server can accurately publish events for followed clubs without spamming users with entire leagues they don't care about.
2. **Milestone 7 (Odds Ingestion)**:
   - Odds provider can prioritize calculating value bets on the user's specific followed clubs and tournaments rather than ingesting thousands of unmonitored matches.
3. **Milestone 8 (Notifications)**:
   - Alert dispatcher can distinguish between a user wanting "all Premier League goals" vs. "only Arsenal goals", dramatically reducing notification fatigue.
