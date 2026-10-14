"""
Seed RAG Knowledge Base Command — Milestone 9.

Loads canonical reference documents for Football, Cricket, and Tennis into the pgvector
knowledge base, including rules, team profiles, player biographies, and tactical terminology.

Usage:
    python manage.py seed_rag_docs [--sport=cricket|football|tennis|all] [--force] [--dry-run]
"""
import sys
from datetime import datetime, timezone
from django.core.management.base import BaseCommand

from sports_platform.rag.ingestion.pipeline import DocumentIngestionPipeline, RawDocument
from sports_platform.sports.models import Sport, Team, Player


SAMPLE_DOCUMENTS = [
    # ══════════════════════════════════════════════════════════════════════════
    # CRICKET
    # ══════════════════════════════════════════════════════════════════════════
    {
        "title": "IPL Powerplay and Field Restriction Rules",
        "document_type": "competition_rules",
        "sport": "cricket",
        "entity_type": "competition",
        "source_url": "https://pulse.internal/cricket/rules/ipl-powerplay",
        "published_at": "2026-03-01T00:00:00Z",
        "content": """
The Indian Premier League (IPL) enforces strict fielding restrictions across a 20-over T20 inning to balance attacking batting opportunities with bowling defense.

Mandatory Powerplay (Overs 1 to 6):
During the first six overs of each inning, a maximum of two fielders are permitted outside the 30-yard fielding circle. The remaining fielders, excluding the bowler and wicketkeeper, must remain within the infield. This restriction encourages explosive scoring at the top of the order, incentivizing openers to loft deliveries over the infield ring.

Non-Powerplay Overs (Overs 7 to 20):
From over 7 onward, a maximum of five fielders are allowed outside the 30-yard circle. If the fielding team fails to start the final over within the stipulated cut-off time (over-rate penalty), they are penalized by being allowed only four fielders outside the circle for the remainder of the inning.

Impact Player Regulation:
Teams are permitted to name five substitutes at the toss and bring in one 'Impact Player' at any break between overs, at the dismissal of a batter, or at the innings break. The Impact Player can bat and bowl their full quota of 4 overs, fundamentally altering tactical depth in T20 batting orders.

No-Balls and Free Hits:
Any front-foot or back-foot no-ball, as well as beamers above waist height, results in an immediate free hit on the subsequent legal delivery. On a free hit, the batter cannot be dismissed by any mode other than run out, obstructing the field, or hitting the ball twice.
        """.strip(),
    },
    {
        "title": "Decision Review System (DRS) and UltraEdge Protocols",
        "document_type": "competition_rules",
        "sport": "cricket",
        "entity_type": "rule",
        "source_url": "https://pulse.internal/cricket/rules/drs-protocol",
        "published_at": "2026-02-15T00:00:00Z",
        "content": """
The Decision Review System (DRS) in international cricket and premier domestic leagues allows on-field decisions to be challenged by either the fielding captain or the dismissed batter.

The 15-Second Window:
The challenging side has exactly 15 seconds from the moment a ball becomes dead to signal for a review by forming a 'T' sign with their arms. Players are strictly forbidden from receiving signals or input from personnel in the dressing room or dugouts.

Review Sequence and Technology:
When an LBW decision is reviewed, the third umpire executes a standardized protocol:
1. Check for a legal delivery (front-foot no-ball check via synchronized stump cameras).
2. UltraEdge / Snickometer audio-visual review: High-frame-rate cameras synchronized with sensitive stump microphones detect sound waves. A sharp spike indicates contact between ball and bat or glove.
3. If no bat contact is confirmed, ball-tracking software (Hawk-Eye) assesses:
   - Pitching: Whether the ball pitched in-line with stumps or outside off-stump (a ball pitching outside leg-stump immediately invalidates LBW).
   - Impact: Whether point of impact on the batter's pad is in-line with stumps.
   - Wickets: The predicted trajectory projecting whether the ball would have hit the stumps or bails.

Umpire's Call Principle:
If less than 50% of the ball is projected to hit the outer edge of the stumps or if the impact point is marginal (more than 3 meters down the pitch), the technology defers to 'Umpire's Call'. In this scenario, the original on-field decision stands, and the reviewing team retains their review.
        """.strip(),
    },
    {
        "title": "Chennai Super Kings (CSK) Team Profile and Tactical Philosophy",
        "document_type": "team_profile",
        "sport": "cricket",
        "entity_type": "team",
        "source_url": "https://pulse.internal/cricket/teams/chennai-super-kings",
        "published_at": "2026-01-10T00:00:00Z",
        "content": """
Chennai Super Kings (CSK) is one of the most successful franchises in Indian Premier League history, having captured five IPL titles (2010, 2011, 2018, 2021, and 2023) alongside two Champions League T20 crowns.

Home Venue and Chepauk Fortress:
CSK plays their home fixtures at the M. A. Chidambaram Stadium (Chepauk) in Chennai. The venue is renowned for its dry, slow-turning surface that heavily rewards finger spinners and cutters from seam bowlers. CSK has established one of the highest home-win percentages in T20 franchise history through specialized spin combinations.

Leadership and Tactical Philosophy:
Under the iconic captaincy of MS Dhoni and long-standing head coach Stephen Fleming, CSK developed a distinctive identity built on calm decision-making, stability in team selection, and backing seasoned international veterans. Rather than constantly churning their roster, CSK emphasizes continuity and clear player roles.

Key Tactical Traits:
- Spin Dominance: Using multi-phase spinners who can bowl in the powerplay and middle overs (such as Ravindra Jadeja, Mitchell Santner, and Moeen Ali).
- Batting Depth: Structuring line-ups where power hitters and all-rounders extend down to position number 9 or 10, enabling aggressive intent throughout the 20 overs.
- Exceptional Chase Execution: Pacing run chases by preserving wickets in hand and capitalizing decisively in overs 16 to 20.
        """.strip(),
    },
    {
        "title": "Virat Kohli Player Biography and Statistical Records",
        "document_type": "player_profile",
        "sport": "cricket",
        "entity_type": "player",
        "source_url": "https://pulse.internal/cricket/players/virat-kohli",
        "published_at": "2026-03-10T00:00:00Z",
        "content": """
Virat Kohli is an Indian international cricketer regarded as one of the greatest modern batsmen across all formats of the game. Born in Delhi in 1988, Kohli captained India to victory in the 2008 ICC Under-19 World Cup before making his senior international debut.

Career Achievements and Milestones:
- 50 ODI Centuries: Kohli became the first cricketer in history to score 50 One Day International centuries, surpassing Sachin Tendulkar's long-standing benchmark during the 2023 ICC Cricket World Cup semi-final.
- IPL All-Time Leading Run Scorer: Representing Royal Challengers Bengaluru (RCB) continuously since the league's inaugural 2008 season, Kohli is the tournament's all-time run-scoring leader with over 8,000 runs, including an unprecedented 973-run campaign in 2016 featuring four centuries.
- ICC Player of the Tournament Honours: Winner of Player of the Tournament awards at the 2014 and 2016 T20 World Cups and the 2023 ODI World Cup.

Batting Technique and Master Chasing:
Kohli is renowned for his supreme physical fitness, quick running between the wickets, and wrist-work through mid-wicket. In limited-overs chases, his average exceeds 65 in successful pursuits, establishing him as one of the premier match finishers in world cricket. His cover drive against high pace and ability to pierce tight infields without taking aerial risks are central to his high-consistency scoring.
        """.strip(),
    },
    {
        "title": "Cricket Terminology: DLS, Yorker, Googly, and Super Over",
        "document_type": "terminology",
        "sport": "cricket",
        "entity_type": "general",
        "source_url": "https://pulse.internal/cricket/glossary",
        "published_at": "2026-01-20T00:00:00Z",
        "content": """
Essential modern cricket concepts and specialized terminology:

Duckworth-Lewis-Stern (DLS) Method:
A mathematical formulation designed to calculate the target score for the team batting second in a limited-overs match interrupted by weather or other delays. The method operates on the principle of 'resources remaining'—treating remaining overs and wickets in hand as combined scoring capacity.

The Yorker:
A delivery pitched at or near the batter's popping crease, arriving directly under the bat at the toes. When executed at high velocity in death overs (overs 16 to 20), the yorker is the most difficult delivery to hit for boundaries because of the extreme difficulty in getting leverage beneath the ball.

The Googly:
A deceptive delivery bowled by a right-arm leg-spin bowler that rotates with wrist action and finger spin to break in the opposite direction (from off to leg for a right-handed batter), confounding expectations of standard leg-spin deviation.

Super Over:
A one-over tiebreaker played when scores are level at the conclusion of a T20 or ODI knockout match. Each team nominates three batters and one bowler. Two wickets ends the batting side's turn. The team that scores the highest number of runs in their single over wins the match.
        """.strip(),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # FOOTBALL
    # ══════════════════════════════════════════════════════════════════════════
    {
        "title": "IFAB Law 11: Offside Rule and Semi-Automated VAR Protocol",
        "document_type": "competition_rules",
        "sport": "football",
        "entity_type": "rule",
        "source_url": "https://pulse.internal/football/rules/law-11-offside",
        "published_at": "2026-02-01T00:00:00Z",
        "content": """
Law 11 of the International Football Association Board (IFAB) Laws of the Game defines the conditions under which a player is penalized for an offside offense.

Offside Position:
A player is in an offside position if any part of their head, body, or feet is in the opponents' half (excluding the halfway line) and nearer to the opponents' goal line than both the ball and the second-last opponent (usually the last defender when the goalkeeper is nearest the goal). Hands and arms of all players are not considered when assessing offside.

Active Involvement:
Being in an offside position is not an offense in itself. A player is only penalized if, at the moment the ball is played or touched by a teammate, they become actively involved in play by:
1. Interfering with play by playing or touching a ball passed or touched by a teammate.
2. Interfering with an opponent by preventing an opponent from playing or being able to play the ball (e.g., obstructing their line of vision, challenging for the ball, or clearly attempting to play the ball when this impacts the opponent).
3. Gaining an advantage by playing the ball or interfering with an opponent after it has rebounded or been deflected off the goalpost, crossbar, or an opponent.

Deliberate Play vs Deflection:
If an attacker in an offside position receives the ball directly from an opponent who 'deliberately played' the ball (having full control and intent to pass or clear), the attacker is not deemed to have gained an illegal advantage and is kept onside.

Semi-Automated Offside Technology (SAOT):
Used in top-tier competitions like UEFA Champions League and Premier League, SAOT uses 12 dedicated tracking cameras mounted under stadium roofs to track the ball and up to 29 data points on each player at 50 times per second, accurately establishing the exact kick-point and skeletal lines within seconds.
        """.strip(),
    },
    {
        "title": "UEFA Champions League Format and Knockout Tournament Rules",
        "document_type": "competition_rules",
        "sport": "football",
        "entity_type": "competition",
        "source_url": "https://pulse.internal/football/rules/ucl-format",
        "published_at": "2026-01-15T00:00:00Z",
        "content": """
The UEFA Champions League operates under the Swiss-system league phase featuring 36 European elite clubs competing in a unified single table.

League Phase Structure:
- Each team plays eight matches (four home and four away) against eight different opponents across four seeding pots.
- The top 8 teams in the 36-team league table qualify automatically for the Round of 16.
- Teams finishing in 9th to 24th place enter a two-legged knockout phase play-off round to secure the remaining eight spots in the Round of 16.
- Teams finishing 25th or lower are eliminated completely from European competition (no drop-down into the Europa League).

Knockout Phase Protocols:
- Two-Legged Ties: Round of 16, quarter-finals, and semi-finals are contested over home-and-away legs.
- Away Goals Rule Abolished: UEFA eliminated the away goals rule across all club competitions. If the aggregate score is tied at the end of regular playing time in the second leg, the tie proceeds to two 15-minute periods of extra time, followed by a penalty shootout if scores remain level.
- Single-Match Final: The Champions League final is held as a neutral-venue single match with extra time and penalties if drawn.
        """.strip(),
    },
    {
        "title": "Arsenal FC Team Profile and Arteta Tactical Structure",
        "document_type": "team_profile",
        "sport": "football",
        "entity_type": "team",
        "source_url": "https://pulse.internal/football/teams/arsenal-fc",
        "published_at": "2026-03-05T00:00:00Z",
        "content": """
Arsenal Football Club, founded in 1886 in Woolwich and based in North London at the Emirates Stadium, is one of English football's most storied institutions with 13 league titles and a record 14 FA Cups.

Historical Milestones:
The club made football history in the 2003-04 Premier League season under Arsène Wenger when 'The Invincibles' completed an entire 38-match league campaign without suffering a single defeat (26 wins, 12 draws).

Mikel Arteta's Tactical Identity:
Under manager Mikel Arteta (appointed in December 2019), Arsenal has established one of European football's most sophisticated positional play (Juego de Posición) systems:
- In-Possession Build-Up (3-2-4-1 Shape): Left-back or defensive midfielder inverts into the double pivot alongside the central defensive midfielder (e.g., Declan Rice), creating numerical superiority in the middle of the pitch.
- Width and Isolation: Wingers Bukayo Saka and Gabriel Martinelli hold high and wide positions to isolate opposition fullbacks in 1v1 situations or combine with overlapping interior midfielders.
- Defensive Solidity and Mid-Block: Arsenal boasts the best defensive record in England by pairing dominant center-backs (William Saliba and Gabriel Magalhães) with aggressive front-foot pressing and rapid counter-pressing triggers when possession is lost.
- Set-Piece Dominance: Guided by set-piece coach Nicolas Jover, Arsenal leads the Premier League in corner-kick and set-play goals through near-post congestion, blocking runners, and outswinging deliveries.
        """.strip(),
    },
    {
        "title": "Real Madrid CF Club History and Champions League Dominance",
        "document_type": "team_profile",
        "sport": "football",
        "entity_type": "team",
        "source_url": "https://pulse.internal/football/teams/real-madrid",
        "published_at": "2026-02-20T00:00:00Z",
        "content": """
Real Madrid Club de Fútbol, founded in 1902 and playing at the Santiago Bernabéu Stadium in Madrid, is widely recognized as the most successful football club in the world.

Record 15 European Cups / Champions Leagues:
Real Madrid holds a peerless continental record, winning 15 European Cup / UEFA Champions League trophies—more than double any other European club. This includes the initial five consecutive titles from 1956 to 1960 led by Alfredo Di Stéfano and Ferenc Puskás, and the historic three-peat under Zinedine Zidane between 2016 and 2018.

Tactical Philosophy and Winning Mentality:
Unlike clubs dogmatically attached to a single tactical dogma, Real Madrid embodies pragmatic excellence and elite game management:
- Transition Lethality: Excels at soaking pressure in a disciplined mid-block and launching vertical counter-attacks utilizing world-class pace and dribbling (Vinícius Júnior, Kylian Mbappé, Rodrygo).
- Midfield Control: Masters game tempo through creative orchestrators such as Jude Bellingham and Luka Modrić who can switch play and unlock low-block defenses.
- Psychological Resilience: Legendary for European comebacks and late-game surges, driven by a cultural expectation of victory in European knockout competitions.
        """.strip(),
    },
    {
        "title": "Erling Haaland Player Profile and Goalscoring Records",
        "document_type": "player_profile",
        "sport": "football",
        "entity_type": "player",
        "source_url": "https://pulse.internal/football/players/erling-haaland",
        "published_at": "2026-03-08T00:00:00Z",
        "content": """
Erling Braut Haaland is a Norwegian professional striker playing for Manchester City and the Norway national team. Known for his devastating physical attributes, aerial power, explosive sprinting pace, and clinical first-time finishing inside the penalty area.

Record-Breaking Premier League Debut:
In his debut 2022-23 Premier League season, Haaland scored 36 goals in 35 appearances, shattering the all-time single-season scoring record previously held by Andy Cole and Alan Shearer (34 goals in 42-game seasons). He contributed 52 goals in all competitions, spearheading Manchester City's historic continental treble (Premier League, FA Cup, and Champions League).

Playstyle and Tactical Role:
Haaland operates as an orthodox number 9 with modern physical traits:
- Box Positioning: Consistently attacks the blind spots of central defenders, targeting the back post or executing lightning darts across the near post.
- Minimalist Efficiency: Frequently completes matches with fewer than 20 touches while registering multiple goals, maximizing shot conversion percentage rather than dropping deep to link play.
- Athleticism: Combines a 6 ft 4 in (1.94 m) frame with acceleration speeds surpassing 35 km/h, overpowering defensive lines on through balls into space.
        """.strip(),
    },
    {
        "title": "Football Tactical Concepts: Expected Goals (xG), False 9, and Gegenpressing",
        "document_type": "terminology",
        "sport": "football",
        "entity_type": "general",
        "source_url": "https://pulse.internal/football/glossary",
        "published_at": "2026-01-25T00:00:00Z",
        "content": """
Key tactical concepts and modern analytics metrics in world football:

Expected Goals (xG):
A predictive statistical metric that measures the quality of a goalscoring opportunity by calculating the probability (between 0.00 and 1.00) that a shot will result in a goal. Factors considered include distance from goal, angle of the shot, body part used (foot vs header), assist type (cross, through ball, rebound), and defender positioning. A penalty kick carries an established benchmark value of 0.76 to 0.79 xG.

The False 9:
A tactical innovation where the nominal central striker regularly vacates the opponent's penalty box and drops deep into central midfield. This creates dilemmas for opposing center-backs: whether to follow the striker (leaving vacated space behind for diagonal wing runners) or stay in line (allowing the false 9 to receive unchallenged between the lines).

Low Block:
A defensive formation where a team retreats deep into its own defensive third, congesting central spaces in front of their penalty area to deny the attacking side space behind the defense. Countering a low block requires rapid ball circulation, switch passes to wing overloads, and cutbacks from bylines.

Gegenpressing (Counter-Pressing):
Popularized in modern German football by Ralf Rangnick and Jürgen Klopp, gegenpressing entails immediate, intense team-wide pressing in the initial 5 to 6 seconds following possession loss. The objective is to win the ball back instantly while the opposing team is discombobulated and transitioning into an attacking posture.
        """.strip(),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # TENNIS
    # ══════════════════════════════════════════════════════════════════════════
    {
        "title": "Grand Slam Scoring Rules, 10-Point Final Set Tiebreak, and Hawk-Eye Live",
        "document_type": "competition_rules",
        "sport": "tennis",
        "entity_type": "rule",
        "source_url": "https://pulse.internal/tennis/rules/grand-slam-scoring",
        "published_at": "2026-02-10T00:00:00Z",
        "content": """
Tennis scoring and technological officiating rules governing Grand Slam competitions (Australian Open, Roland Garros, Wimbledon, and US Open):

Match Format:
- Men's singles in Grand Slam tournaments are contested as best-of-five sets.
- Women's singles and doubles matches are contested as best-of-three sets.

Game and Set Scoring:
Points advance from Love (0) to 15, 30, and 40. A score of 40-40 is called Deuce. From deuce, a player must win two consecutive points: Advantage followed by Game. A set is won by the first player to win 6 games with a margin of at least two games (e.g., 6-4). At 6-6, a 7-point tiebreak is played (first to 7 points with a 2-point lead).

Unified 10-Point Final Set Tiebreak:
In 2022, all four Grand Slam tournaments adopted a harmonized tiebreak rule for deciding sets (the 5th set in men's singles, or the 3rd set in women's singles). When the final set reaches 6-6 in games, the match is decided by a 10-point super tiebreak. The winner is the first player to reach 10 points leading by two points or more.

Hawk-Eye Live Electronic Line Calling:
Modern Grand Slams and ATP/WTA Tour events utilize Hawk-Eye Live, replacing traditional human line umpires with automated optical camera tracking systems. Twelve to eighteen synchronized high-speed cameras track the ball's trajectory in 3D real time, instantly triggering automated audio 'OUT' or 'FAULT' calls within milliseconds of the ball landing outside the boundary lines, eliminating human error on close line calls.
        """.strip(),
    },
    {
        "title": "Novak Djokovic Player Profile and Grand Slam Records",
        "document_type": "player_profile",
        "sport": "tennis",
        "entity_type": "player",
        "source_url": "https://pulse.internal/tennis/players/novak-djokovic",
        "published_at": "2026-03-02T00:00:00Z",
        "content": """
Novak Djokovic is a Serbian professional tennis player who holds the all-time men's record with 24 Grand Slam singles titles and over 420 weeks ranked as ATP World No. 1.

Unprecedented Tennis Milestones:
- 24 Grand Slam Singles Titles: Australian Open (10 titles - all-time record), Wimbledon (7), US Open (4), Roland Garros (3).
- Career Golden Masters: The only player in tennis history to have won all nine ATP Masters 1000 tournaments—a feat he has accomplished twice.
- 40 ATP Masters 1000 Titles: All-time leader in Masters 1000 tournament victories.
- Olympic Gold Medal: Completed the Career Golden Slam by claiming the Men's Singles Gold Medal at the 2024 Paris Olympic Games.

Playing Style and Technical Superiority:
- The Greatest Return in Tennis History: Neutralizes opposing 130+ mph serves through anticipation, flexibility, and depth of return straight to the server's shoelaces.
- Two-Handed Backhand: Widely regarded as the most stable and penetrating backhand in the sport, equally dangerous when redirected cross-court or fired flat down the line.
- Baseline Stamina and Flexibility: Renowned for extreme physical flexibility and sliding on hard courts, retrieving balls from defensive corners that other players cannot reach and converting defense into attack with a single stroke.
        """.strip(),
    },
    {
        "title": "Carlos Alcaraz Player Profile and Multi-Surface Mastery",
        "document_type": "player_profile",
        "sport": "tennis",
        "entity_type": "player",
        "source_url": "https://pulse.internal/tennis/players/carlos-alcaraz",
        "published_at": "2026-03-04T00:00:00Z",
        "content": """
Carlos Alcaraz Garfia is a Spanish professional tennis player who made history by becoming the youngest ATP World No. 1 in history at age 19 after winning the 2022 US Open.

Multi-Surface Grand Slam Triumphs:
By age 21, Alcaraz accomplished the rare feat of capturing Grand Slam titles on all three primary tennis surfaces:
- Hard Court: US Open champion (2022).
- Grass Court: Wimbledon champion (2023, 2024), defeating Novak Djokovic in thrilling finals.
- Clay Court: Roland Garros champion (2024), demonstrating tactical slide mechanics and point construction.

Technical Attributes and Athleticism:
- Explosive Forehand: Generates extreme racket head speed producing heavy topspin mixed with 100+ mph flat winners from anywhere on the court.
- The Disguised Drop Shot: Possesses the most lethal drop shot in modern tennis, executed with identical backswing mechanics to his heavy topspin groundstrokes, repeatedly catching deep-sitting baseline opponents off balance.
- Court Coverage: Unrivaled sprint speed and athletic elasticity, frequently executing reflex volleys and passing shots on the full dead run.
        """.strip(),
    },
    {
        "title": "Tennis Terminology: Break Points, Kick Serves, and Surface Characteristics",
        "document_type": "terminology",
        "sport": "tennis",
        "entity_type": "general",
        "source_url": "https://pulse.internal/tennis/glossary",
        "published_at": "2026-01-30T00:00:00Z",
        "content": """
Essential tennis tactical terminology and court physics:

Break Point:
A situation in a game where the receiving player is one point away from winning the game against the server's serve (e.g., 30-40, 15-40, 0-40, or Advantage Receiver). Breaking serve is the primary mechanism by which players gain advantages in a set, as holding serve is the expected statistical outcome on professional tours.

Kick Serve (Topspin Serve):
A specialized serve struck with upward brush across the back and side of the ball, imparting heavy topspin. Upon bouncing in the service box, the ball leaps sharply upward and away from a right-handed returner's backhand, forcing the opponent to hit high out of their optimal strike zone.

Court Surface Characteristics:
- Clay Courts (Roland Garros): High friction with crushed brick top dressing. Slows ball pace considerably after the bounce while producing high, kicking bounces. Favors heavy topspin, slide mobility, and extended physical baseline rallies.
- Grass Courts (Wimbledon): Low coefficient of friction. Ball skids low off the grass with reduced bounce height and higher velocity, heavily rewarding powerful first serves, slice backhands, and net play.
- Hard Courts (Australian Open, US Open): Acrylic surface over asphalt or concrete providing medium-fast to fast speed with consistent, true bounces. Demands versatile all-court technical balance.
        """.strip(),
    },
]


class Command(BaseCommand):
    help = "Seeds canonical sports knowledge documents for Cricket, Football, and Tennis into pgvector RAG pipeline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sport",
            type=str,
            default="all",
            choices=["all", "cricket", "football", "tennis"],
            help="Filter documents to ingest by sport.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-ingestion and re-chunking of documents even if content hash exists.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate ingestion without writing to the database.",
        )

    def handle(self, *args, **options):
        sport_filter = options.get("sport", "all").lower()
        force = options.get("force", False)
        dry_run = options.get("dry_run", False)

        self.stdout.write(self.style.MIGRATE_HEADING("=== Seeding RAG Knowledge Base ==="))

        docs_to_ingest = SAMPLE_DOCUMENTS
        if sport_filter != "all":
            docs_to_ingest = [d for d in SAMPLE_DOCUMENTS if d.get("sport", "").lower() == sport_filter]

        self.stdout.write(f"Preparing to ingest {len(docs_to_ingest)} documents (sport filter: {sport_filter})...\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: No records will be modified."))
            for doc in docs_to_ingest:
                self.stdout.write(f"  - [{doc['document_type']}] {doc['title']} ({doc['sport']})")
            return

        pipeline = DocumentIngestionPipeline()
        ingested_count = 0
        skipped_count = 0

        for doc_data in docs_to_ingest:
            raw_doc = RawDocument(
                title=doc_data["title"],
                content=doc_data["content"],
                source_url=doc_data.get("source_url", ""),
                document_type=doc_data.get("document_type", "article"),
                sport=doc_data.get("sport"),
                entity_type=doc_data.get("entity_type", ""),
                published_at=doc_data.get("published_at"),
            )

            try:
                doc_id = pipeline.ingest(raw_doc, force_reindex=force)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Ingested: {doc_data['title']} (ID: {doc_id})"))
                ingested_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Failed to ingest '{doc_data['title']}': {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== Completed RAG seeding! Ingested/Verified: {ingested_count} documents. ==="
            )
        )
