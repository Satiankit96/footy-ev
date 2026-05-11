# Technical Blue Map: Local-First +EV Sports Betting System (Free-Tier Edition)

> Architecture, data model, code skeletons, and critique of the local-first approach.
> Target market: European football pre-match (phase 1); player props (phase 2).
> All tooling free. See `COSTS.md` for the cost reality.

---

## Section 1 — Where This Architecture Will Fail (And How to Mitigate)

Before any design, a hostile review of what will break. If you don't plan for these, the project dies in month 2.

### 1.1 Failure mode: the edge is already priced in

The majority of "alpha" ideas a data scientist comes up with on day one (rolling xG, rest days, home advantage, recent form) are already in the closing line at sharp books. A model that perfectly predicts match outcomes using public historical data will **still lose to the vig** because Kalshi's closing price has already aggregated that same information.

**Mitigation:** Treat the de-vigged closing line as the truth and hunt for *where your model systematically disagrees with it and is right over a large sample*. The operational question is never "is my model accurate?" but "does my model disagree with the market in ways that beat the close?" Every backtest must compute Closing Line Value (CLV) as its primary metric. Raw P&L is secondary.

### 1.2 Failure mode: account limiting kills the strategy before it can compound

A common pattern: system finds real edge, bettor ramps up stakes at soft books, gets limited to $5 max bet within 4–8 weeks, strategy becomes uneconomic. This is the default outcome if you don't design for it.

**Mitigation:** Route primary execution to Kalshi (CFTC-regulated; exchange-style contracts traded between users, not against the house). Kalshi is exchange-style (binary contracts traded between users), so the winner-limiting failure mode does not apply — accounts are not restricted for consistent profit.

### 1.3 Failure mode: data pipeline breaks silently and you trade on stale inputs

Scrapers break when websites change HTML. APIs throttle. You will place bets based on yesterday's injury report because a Playwright selector silently returned an empty list.

**Mitigation:** Every data source must have (a) a staleness timestamp, (b) a row-count sanity check vs historical mean, and (c) a circuit breaker that halts live trading if freshness > T minutes. This is not optional.

### 1.4 Failure mode: local LLMs hallucinate entities and poison the RAG layer

Llama 3.1 8B, even DeepSeek-V3 at 37B activated params, will confidently misattribute quotes, invent injuries, and merge similar player names ("Lucas Paquetá" vs "Lucas Moura"). If you feed their output into features without validation, you are injecting noise at scale.

**Mitigation:** Always use structured output (JSON schema, pydantic validators), always cross-check entities against a canonical player/team table, always flag low-confidence extractions for human review before they enter the feature store.

**Free-tier extraction stack:** Default to Ollama + Llama 3.1 8B for offline parsing. When Ollama quality is insufficient (long articles, ambiguous tactical language), fall back to **Gemini 2.5 Flash via the free API tier** — the free quota (~1500 req/day) is more than enough for this project's extraction volume, and 2.5 Flash matches or exceeds local 8B models on structured extraction tasks. Routing logic lives in `src/footy_ev/llm/router.py`; selection driven by `LLM_EXTRACTOR` env var. Either way, the same pydantic validation gate applies — never trust LLM output, always validate.

### 1.5 Failure mode: overfitting disguised as "feature engineering"

You will feel productive adding 200 features. The model will look brilliant on holdout. Then it will fall over in live trading. Standard ML-pipeline self-deception.

**Mitigation:** Strictly walk-forward splits. Every added feature must justify itself via (a) out-of-sample SHAP importance, (b) permutation-importance vs a shuffled baseline, and (c) a domain rationale written down in a `features.md` file *before* you train. If you can't articulate why a feature should have predictive power, it doesn't.

### 1.6 Failure mode: bankroll ruin from noisy Kelly estimates

Kelly is mathematically optimal *given a known edge*. Your edge is estimated with uncertainty. Full Kelly on an estimated edge has ~30% probability of hitting 50% drawdown even when the true edge is real. This destroys most amateur systems.

**Mitigation:** Fractional Kelly at 0.10–0.25 of full Kelly, with the fraction itself dynamically reduced when recent CLV variance widens. Enforce a hard per-bet cap (1–2% of bankroll) regardless of Kelly output.

---

## Section 2 — Multi-Agent Topology (LangGraph)

### 2.1 Topology at a glance

```
                        ┌─────────────────┐
                        │   Orchestrator  │◄──── LangGraph state machine
                        │   (StateGraph)  │      (cyclical, checkpointed)
                        └────────┬────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           │                     │                     │
           ▼                     ▼                     ▼
    ┌────────────┐        ┌─────────────┐       ┌──────────────┐
    │  Scraper   │        │   Analyst   │       │   News/NLP   │
    │   Agent    │        │   Agent     │       │    Agent     │
    └─────┬──────┘        └──────┬──────┘       └──────┬───────┘
          │                      │                     │
          ▼                      ▼                     ▼
     odds snapshots       model probabilities    lineup/injury deltas
          │                      │                     │
          └──────────────────────┼─────────────────────┘
                                 ▼
                        ┌─────────────────┐
                        │  Pricing Agent  │  (de-vig, compare to market)
                        └────────┬────────┘
                                 ▼
                        ┌─────────────────┐
                        │   Risk Agent    │  (Kelly fraction, caps, CLV check)
                        └────────┬────────┘
                                 ▼
                        ┌─────────────────┐
                        │  Execution      │  (Betfair API primary)
                        │  Router         │
                        └─────────────────┘
```

### 2.2 Why this is structurally different from Gemini's proposal

Gemini proposed the classic "Supervisor arbitrating ML vs sentiment" pattern. I'm proposing a **pipeline with one designated probability producer (the Analyst)**, with News/NLP feeding into the Analyst's feature set rather than competing with it at decision time. Reasons:

1. **There should be one number for P(event).** If the Analyst says 48% and the Sentiment agent says 55%, a supervisor picking between them or averaging them produces an uncalibrated output. Better: the 55% is because sentiment detected a late-breaking lineup change that updates the Poisson rate parameter, so the Analyst re-runs with updated inputs and emits one coherent 55%.

2. **Calibration is a per-model property.** Two separately-calibrated models don't compose into a calibrated joint output without retraining the joint. Stacking isotonic on top of a weighted average is a mess.

3. **Market-consistent pricing is the goal**, not "agreement." The Pricing agent's job is to compare the Analyst's calibrated probability to the market's de-vigged probability and decide if there's edge. News/sentiment is a feature, not a vote.

### 2.3 LangGraph State and Node Skeleton

```python
"""
LangGraph state machine for the betting pipeline.
Checkpointed to DuckDB for replay and debugging.
"""
from __future__ import annotations
from typing import Annotated, Literal, TypedDict
from operator import add
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver  # or DuckDB-backed custom
from pydantic import BaseModel, Field


# ----------------------------- Domain types ----------------------------- #
class MarketType(str, Enum):
    MATCH_1X2 = "1x2"
    OU_25 = "over_under_2.5"
    BTTS = "btts"
    ASIAN_HCP = "asian_handicap"
    PLAYER_GOALS = "player_anytime_goal"


class OddsSnapshot(BaseModel):
    venue: str               # e.g. "betfair_exchange", "pinnacle_scrape"
    fixture_id: str
    market: MarketType
    selection: str           # "home" / "draw" / "away" / "over" / etc.
    odds_decimal: float
    captured_at: datetime
    liquidity_gbp: float | None = None   # for exchange


class ModelProbability(BaseModel):
    fixture_id: str
    market: MarketType
    selection: str
    p_raw: float             # pre-calibration
    p_calibrated: float      # post-isotonic
    model_version: str
    features_hash: str       # for reproducibility
    uncertainty_se: float    # bootstrap SE of p_calibrated


class BetDecision(BaseModel):
    fixture_id: str
    market: MarketType
    selection: str
    odds_taken: float
    stake_gbp: Decimal
    kelly_fraction_used: float
    model_edge_pct: float    # (p_cal * odds) - 1
    decided_at: datetime
    venue: str
    rationale: str           # short text audit trail


# ----------------------------- Graph state ----------------------------- #
class BettingState(TypedDict, total=False):
    """
    The state passed between nodes in the LangGraph.
    All fields are optional because the graph runs partially on each tick.
    """
    # Inputs
    fixtures_to_process: list[str]       # fixture_ids queued for this tick
    as_of: datetime                      # freezes the point-in-time cutoff

    # Intermediate artifacts
    odds_snapshots: Annotated[list[OddsSnapshot], add]     # append-only per tick
    news_deltas: Annotated[list[dict], add]                # lineup/injury events
    model_probs: Annotated[list[ModelProbability], add]

    # Decisions
    candidate_bets: list[BetDecision]
    placed_bets: list[BetDecision]

    # Control plane
    circuit_breaker_tripped: bool
    data_freshness_seconds: dict[str, int]   # per-source
    last_error: str | None


# ----------------------------- Nodes ----------------------------- #
def scraper_node(state: BettingState) -> BettingState:
    """
    Pulls odds from Betfair Exchange API + any scraped books.
    Enforces freshness; trips circuit breaker on staleness.
    """
    new_snapshots: list[OddsSnapshot] = []
    freshness: dict[str, int] = {}
    for fixture_id in state["fixtures_to_process"]:
        # betfair_exchange.fetch_odds(...) and scrapers go here
        # (each source returns its own List[OddsSnapshot])
        pass
    staleness_limit_sec = 300
    tripped = any(s > staleness_limit_sec for s in freshness.values())
    return {
        "odds_snapshots": new_snapshots,
        "data_freshness_seconds": freshness,
        "circuit_breaker_tripped": tripped,
    }


def news_node(state: BettingState) -> BettingState:
    """
    Local LLM parses news/tweets into structured deltas
    (injury, lineup change, weather). Output validated via pydantic.
    """
    deltas: list[dict] = []
    # Ollama call with JSON schema -> validated -> canonicalized entity IDs
    return {"news_deltas": deltas}


def analyst_node(state: BettingState) -> BettingState:
    """
    For each (fixture, market), produces calibrated probability.
    Pipeline: feature_snapshot -> (Dixon-Coles | xG-Skellam | XGBoost)
              -> isotonic_calibration -> bootstrap_uncertainty.
    """
    if state.get("circuit_breaker_tripped"):
        return {"model_probs": []}
    probs: list[ModelProbability] = []
    # ... per-market model dispatch
    return {"model_probs": probs}


def pricing_node(state: BettingState) -> BettingState:
    """
    De-vig market odds (Shin or power method via goto_conversion library),
    compute edge = p_calibrated * odds_best_available - 1, produce candidate bets.
    """
    candidates: list[BetDecision] = []
    edge_threshold = 0.03  # 3% after commission
    for prob in state.get("model_probs", []):
        # find best available odds across venues for same selection
        # compute edge; if > threshold, add candidate
        pass
    return {"candidate_bets": candidates}


def risk_node(state: BettingState) -> BettingState:
    """
    Applies fractional Kelly, per-bet cap, drawdown-aware fraction adjustment,
    total daily exposure cap. May drop or downsize candidates.
    """
    approved: list[BetDecision] = []
    # See §4 for formulas
    return {"placed_bets": approved}  # not yet placed; execution router does it


def execution_node(state: BettingState) -> BettingState:
    """
    Routes each approved bet to primary venue (Betfair Exchange by default).
    Logs odds taken vs quoted; flags slippage > 2%.
    """
    # betfair_api.place_bet(...) with idempotency key = hash(decision)
    return {}


# ----------------------------- Graph assembly ----------------------------- #
def build_graph() -> StateGraph:
    g = StateGraph(BettingState)
    g.add_node("scraper", scraper_node)
    g.add_node("news", news_node)
    g.add_node("analyst", analyst_node)
    g.add_node("pricing", pricing_node)
    g.add_node("risk", risk_node)
    g.add_node("execution", execution_node)

    g.set_entry_point("scraper")
    # scraper and news run in parallel, fan-in at analyst
    g.add_edge("scraper", "analyst")
    g.add_edge("news", "analyst")
    g.add_edge("analyst", "pricing")
    g.add_edge("pricing", "risk")
    g.add_edge("risk", "execution")
    g.add_edge("execution", END)

    return g


if __name__ == "__main__":
    # Smoke test: dry-run with an empty fixture list.
    graph = build_graph().compile()
    out = graph.invoke({
        "fixtures_to_process": [],
        "as_of": datetime.now(timezone.utc),
        "circuit_breaker_tripped": False,
    })
    print(out)
```

### 2.4 How conflicting signals are actually handled

In the rare case where News/NLP detects something (e.g., star striker out) *after* the Analyst has already priced the fixture with yesterday's lineup, the graph's cyclical capability is used: News writes a delta, Analyst re-runs for affected fixtures only (idempotent keyed on fixture_id + features_hash), pricing re-evaluates. There is **never a weighted vote between two probabilities for the same event.** If they disagree, one is stale, and the fix is to re-run with the latest inputs rather than average.

---

## Section 3 — Data Alpha: Three "Leaky" Data Points in Football Markets

Gemini asked about player props specifically. I'm going to answer for football broadly because (a) you said start with European football and (b) player props in football (not NFL/NBA) are low-liquidity and limited early, so your early edge is in match-level markets. I'll tag which of these extend cleanly to props.

### 3.1 Late lineup churn in leagues where lineups post ~1 hour before kickoff

Most books price markets based on expected lineups. In Premier League, starting XI is announced ~60 minutes pre-kickoff. There is a well-documented window where soft books lag Betfair Exchange by 5–20 minutes in re-pricing. The signal is not "star player out" (everyone prices this fast) — it's **unexpected tactical changes**: a box-to-box midfielder shifted to a false-9 position, a defensive setup with three CBs when they usually play four, etc. These change expected possession share and xG distributions in ways that scalar injury models miss.

**Operationalizing:** Scrape starting XIs and build a "formation delta" feature: cosine distance between the current expected formation (based on last 5 matches) and the announced formation. Feed into the Analyst as a feature and also as a trigger for a re-run cycle.

**RAG angle (Gemini's question):** Local LLM (with JSON schema) parses tactical-analysis posts from verified accounts (The Athletic, Opta analysts, club-affiliated journalists) into `{player_id, role_change, confidence}`. This is genuinely a case where an LLM adds value because tactical role is ambiguous text, not a number.

### 3.2 Reverse line movement against sharp money

When Betfair Exchange money flows one way but soft-book odds drift the other way, it indicates that soft books are being "balanced" by recreational action while sharps are loaded on the other side. This has been a workable signal in football for years, especially in mid-table Bundesliga/Serie A fixtures where public attention is lower.

**Operationalizing:** Store every 5-minute odds snapshot per market per venue. Compute, per fixture-market-selection, the time-series of `(p_betfair - p_softbook_avg)`. When this diverges by >2% and Betfair volume is above the per-fixture median, flag for higher Analyst attention and possible bet.

**Prop extension:** For player props (goalscorer, shots on target), the same logic works comparing Betfair Exchange's thin prop markets against PrizePicks/Underdog-style fixed lines.

### 3.3 "Set-piece coach" effects that haven't propagated

Studies (Stats Perform internal work, plus several academic papers) show that teams that hire a dedicated set-piece coach produce a measurable uplift in set-piece xG over 10–20 matches, but market-implied probabilities on corners/set-piece-goal markets don't price this in for several months. Brentford is the canonical example. This is a genuinely leaky data point because books don't systematically track coaching-staff changes below the head-coach level.

**Operationalizing:** Maintain a hand-curated `staff_changes.csv` of set-piece and analytics appointments (sources: club press releases, trusted football journalists via RAG). Compute a "set-piece coach tenure" feature and test its SHAP importance on corners/set-piece-goal markets.

### 3.4 How local RAG feeds these variables into XGBoost

The pipeline for each leaky data point is:

```
raw text (tweet, article, press release)
    → local LLM with JSON schema extraction
    → pydantic validation + canonical entity resolution (fuzzy-match vs players/teams table)
    → timestamped write to DuckDB `events_ledger`
    → feature view: e.g., `set_piece_coach_tenure_days(team_id, as_of)`
    → feature matrix for XGBoost via DuckDB query parameterized on `as_of`
```

Key engineering note: **the extraction step runs in a different process from the model**. You never let the LLM's output directly reach the model — it always passes through the validated event ledger. This gives you replayability (recompute features from the ledger at any point in time) and auditability (why did we place that bet).

---

## Section 4 — Risk & Bankroll Engine

### 4.1 Fractional Kelly with model uncertainty

Full Kelly staking: `f* = (b·p - q) / b` where `b = odds_decimal - 1`, `p = P(win)`, `q = 1 - p`.

Full Kelly assumes `p` is known. It isn't — your model produces `p̂` with standard error `σ_p`. The standard correction is **"Kelly on the lower bound":** stake as if your edge is `p̂ - k·σ_p` for some conservatism factor `k` (typical: 1.0–1.5, corresponding to ~68–87% confidence the true p is at least that high).

In practice, layer three adjustments:

```python
def kelly_stake(
    p_hat: float,          # calibrated probability
    sigma_p: float,        # bootstrap SE of p_hat
    odds_decimal: float,
    bankroll: float,
    base_fraction: float = 0.25,     # fractional Kelly default
    uncertainty_k: float = 1.0,      # std-dev haircut
    per_bet_cap_pct: float = 0.02,   # hard cap 2%
    recent_clv_pct: float = 0.0,     # rolling 100-bet CLV
) -> float:
    """
    Returns stake in bankroll currency units.
    All three adjustments stack:
      1. Shrink p_hat by uncertainty.
      2. Scale Kelly by base_fraction (quarter Kelly).
      3. Scale further if recent CLV is deteriorating.
      4. Hard cap at per_bet_cap_pct of bankroll.
    """
    # 1. Lower-bound the win probability
    p_lb = max(0.0, p_hat - uncertainty_k * sigma_p)

    # 2. Full Kelly on the lower-bounded p
    b = odds_decimal - 1.0
    if b <= 0 or p_lb <= 0:
        return 0.0
    q = 1.0 - p_lb
    f_full = (b * p_lb - q) / b
    if f_full <= 0:
        return 0.0

    # 3. Fractional Kelly, with CLV-aware shrinkage
    #    If recent CLV is positive, we earned the right to use base_fraction.
    #    If flat to negative, we shrink toward 10%.
    clv_multiplier = max(0.4, min(1.0, 0.5 + 10.0 * recent_clv_pct))
    f_used = base_fraction * clv_multiplier * f_full

    # 4. Per-bet hard cap
    f_used = min(f_used, per_bet_cap_pct)

    return f_used * bankroll
```

The CLV-multiplier here is the concrete answer to Gemini's "dynamically adjust the Kelly Fraction based on historical backtesting variance" — instead of using backtest variance (which is a lagging, gameable quantity), use live CLV on the last 100 real bets as the real-time signal of whether the edge is still live.

### 4.2 Portfolio-level caps

Per-bet caps alone are insufficient because correlated bets (e.g., overs in three consecutive Liverpool matches) compound drawdown risk. Enforce:

- **Per-day exposure cap:** e.g., 10% of bankroll.
- **Per-fixture exposure cap:** e.g., 3% of bankroll across all markets on one fixture.
- **Correlated-bet flag:** if two candidates share >70% outcome correlation (e.g., Over 2.5 goals and BTTS in the same match), treat them as one bet for cap purposes.

### 4.3 Ruin simulation requirement

Before going live, run 10,000 Monte Carlo simulations of the system using your backtested edge and variance. Report P(50% drawdown) and P(bankroll < 50% bankroll after 1000 bets). If either is >5%, shrink `base_fraction` until it isn't.

---

## Section 5 — The "Ghost Execution" Question, Reframed

Gemini asked how to build a layer that mimics human betting behavior to avoid limits. I will not design that, and my reasoning is in `PROJECT_INSTRUCTIONS.md` §4. What I'll design instead is the **venue router** — the legitimate structural answer to the same underlying problem.

### 5.1 Venue Router Design

Operator is NY-based. Only CFTC-regulated venues are legal. This simplifies
the routing problem to a single execution path:

```
For each approved bet:

  1. Kalshi (KalshiEX)
       - Only execution target. CFTC-regulated prediction exchange.
       - Exchange-style: binary contracts between users; no house edge
         on the exchange side beyond the small taker fee (~1–2%).
       - Check available liquidity at your target stake; if insufficient,
         fill what's available and log the residual as unexecuted.
       - No account-limiting risk: consistent winning does not trigger
         restriction because Kalshi is not the counterparty.
       - CLV benchmark: Kalshi closing price (the last-traded price
         before contract resolution).

There is no tier 2 or tier 3. Non-US venues (Betfair, Pinnacle live,
Polymarket) are not accessible from NY without legal risk. Soft US
sportsbooks are not included because they limit winners. Kalshi is the
correct structural answer to both the limiting problem and the
jurisdiction problem simultaneously.
```

### 5.2 What not to do

- No non-US venues. No Betfair Exchange, Pinnacle live API, Polymarket, or offshore books.
- No multi-accounting on a single venue under multiple names / addresses.
- No VPN-based geo-evasion of regional restrictions.
- No automated click-timing randomization that exists solely to make an automated bet look manual. (Placing bets via an API key the venue issued you is fine; evading a venue's automation detection on their web UI is not.)

---

## Section 6 — DuckDB Schema

### 6.1 Design principles

- **Point-in-time everything.** Every row has a `captured_at` or `event_timestamp` and feature views filter on it.
- **Append-only ledgers** for odds and events. No updates, no deletes. Restating the past is not allowed.
- **Derived tables are views** materialized nightly; raw ledgers are the source of truth.
- **One file per partition.** Parquet partitioned by league × season for historical, by date for live.

### 6.2 Schema

```sql
-- =========================================================================
-- RAW LEDGERS (append-only)
-- =========================================================================

CREATE TABLE IF NOT EXISTS fixtures (
    fixture_id        VARCHAR PRIMARY KEY,
    league            VARCHAR NOT NULL,           -- EPL, LL, SA, BL, L1, ...
    season            VARCHAR NOT NULL,           -- "2025-2026"
    kickoff_utc       TIMESTAMP NOT NULL,
    home_team_id      VARCHAR NOT NULL,
    away_team_id      VARCHAR NOT NULL,
    venue_id          VARCHAR,
    status            VARCHAR NOT NULL,           -- scheduled/live/final
    home_score_ft     INTEGER,
    away_score_ft     INTEGER,
    home_xg           DOUBLE,
    away_xg           DOUBLE,
    ingested_at       TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    team_id           VARCHAR PRIMARY KEY,
    team_name         VARCHAR NOT NULL,
    country           VARCHAR NOT NULL,
    aliases           VARCHAR[],                  -- for entity resolution
    ingested_at       TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    player_id         VARCHAR PRIMARY KEY,
    full_name         VARCHAR NOT NULL,
    team_id           VARCHAR NOT NULL,
    position          VARCHAR,
    aliases           VARCHAR[],
    ingested_at       TIMESTAMP NOT NULL
);

-- Append-only odds snapshots. This is the biggest table; partition externally.
CREATE TABLE IF NOT EXISTS odds_snapshots (
    snapshot_id       VARCHAR PRIMARY KEY,        -- uuid
    captured_at       TIMESTAMP NOT NULL,
    venue             VARCHAR NOT NULL,           -- 'betfair_ex', 'pinnacle_scrape', 'bet365_scrape'
    fixture_id        VARCHAR NOT NULL REFERENCES fixtures(fixture_id),
    market            VARCHAR NOT NULL,           -- '1x2', 'ou25', 'btts', 'ah_-1.5', 'player_goal'
    selection         VARCHAR NOT NULL,           -- 'home', 'over', 'yes', 'player:salah_mohammed'
    odds_decimal      DOUBLE NOT NULL,
    liquidity_gbp     DOUBLE,                     -- only exchanges
    book_margin_pct   DOUBLE,                     -- derivable but cache it
    is_closing        BOOLEAN DEFAULT FALSE       -- set TRUE on final pre-kickoff snapshot
);
CREATE INDEX idx_odds_fixture_market_time
    ON odds_snapshots (fixture_id, market, captured_at);

-- Append-only events ledger (injuries, lineups, weather, coaching changes, etc.)
CREATE TABLE IF NOT EXISTS events_ledger (
    event_id          VARCHAR PRIMARY KEY,
    event_type        VARCHAR NOT NULL,           -- 'injury', 'lineup', 'set_piece_coach_hire', ...
    fixture_id        VARCHAR,                    -- nullable: some events are team-level
    team_id           VARCHAR,
    player_id         VARCHAR,
    payload           JSON NOT NULL,              -- event-type-specific
    source            VARCHAR NOT NULL,           -- 'opta', 'tweet:handle', 'press_release'
    source_confidence DOUBLE,                     -- llm-assigned 0..1
    effective_from    TIMESTAMP NOT NULL,         -- when the event is true in the world
    ingested_at       TIMESTAMP NOT NULL          -- when we found out (lookahead check)
);
CREATE INDEX idx_events_fixture_time
    ON events_ledger (fixture_id, effective_from);

-- =========================================================================
-- MODEL OUTPUTS (append-only)
-- =========================================================================

CREATE TABLE IF NOT EXISTS model_predictions (
    prediction_id     VARCHAR PRIMARY KEY,
    fixture_id        VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    selection         VARCHAR NOT NULL,
    p_raw             DOUBLE NOT NULL,
    p_calibrated      DOUBLE NOT NULL,
    sigma_p           DOUBLE NOT NULL,            -- bootstrap SE
    model_version     VARCHAR NOT NULL,
    features_hash     VARCHAR NOT NULL,           -- hash of input feature vector
    as_of             TIMESTAMP NOT NULL,         -- point-in-time cutoff used
    generated_at      TIMESTAMP NOT NULL
);

-- =========================================================================
-- BET DECISIONS AND SETTLEMENT
-- =========================================================================

CREATE TABLE IF NOT EXISTS bet_decisions (
    decision_id       VARCHAR PRIMARY KEY,
    prediction_id     VARCHAR NOT NULL REFERENCES model_predictions(prediction_id),
    fixture_id        VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    selection         VARCHAR NOT NULL,
    venue             VARCHAR NOT NULL,
    odds_quoted       DOUBLE NOT NULL,
    odds_taken        DOUBLE,                     -- may differ (slippage)
    stake_gbp         DECIMAL(18,2) NOT NULL,
    kelly_fraction    DOUBLE NOT NULL,
    model_edge_pct    DOUBLE NOT NULL,
    decided_at        TIMESTAMP NOT NULL,
    placed_at         TIMESTAMP,
    status            VARCHAR NOT NULL,           -- candidate/placed/rejected/settled/voided
    settlement        VARCHAR,                    -- win/loss/push/void
    pnl_gbp           DECIMAL(18,2),
    closing_odds      DOUBLE,                     -- filled in post-kickoff
    clv_pct           DOUBLE                      -- (odds_taken/closing_odds - 1)
);

-- =========================================================================
-- POINT-IN-TIME FEATURE VIEWS
-- =========================================================================

-- Rolling xG-for/xG-against features per team, queryable as-of any timestamp.
-- Pass :as_of as the cutoff to ensure no lookahead.
CREATE VIEW v_team_xg_rolling AS
SELECT
    f.home_team_id AS team_id,
    f.kickoff_utc,
    f.fixture_id,
    AVG(f.home_xg) OVER w AS xg_for_roll5,
    AVG(f.away_xg) OVER w AS xg_against_roll5
FROM fixtures f
WHERE f.status = 'final'
WINDOW w AS (
    PARTITION BY f.home_team_id
    ORDER BY f.kickoff_utc
    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING   -- strictly prior matches
);
-- Repeat for away; union; then aggregate per (team_id, as_of).

-- Latest odds per (fixture, market, selection, venue) as of a given timestamp.
-- Parameterize via DuckDB's prepared statement or templating.
-- SELECT ... WHERE captured_at <= :as_of
--   QUALIFY ROW_NUMBER() OVER (PARTITION BY fixture_id, market, selection, venue
--                              ORDER BY captured_at DESC) = 1;
```

### 6.3 Real-time + historical in the same store

DuckDB handles both because it supports zero-copy reads over Parquet. Pattern:

- **Historical:** Parquet files partitioned by `league/season/` on disk. Read-only. Used for backtesting and training.
- **Live:** an in-process DuckDB database written to by the Scraper node, with a scheduled `COPY ... TO 'path/to/parquet'` to archive nightly.
- **Unified views:** `CREATE VIEW v_odds_all AS SELECT * FROM parquet_scan('archive/**/*.parquet') UNION ALL SELECT * FROM odds_snapshots_live;` — your model code queries `v_odds_all` and doesn't care which side the data came from.

---

## Section 7 — Validation, Feature Selection, Model Choice, Calibration

### 7.1 Walk-forward validation in DuckDB

```python
"""
Walk-forward CV tailored for European football.
Each season is a fold; within-season you expand the training window match by match.
"""
import duckdb
import pandas as pd
from datetime import date

def walk_forward_splits(
    con: duckdb.DuckDBPyConnection,
    league: str,
    train_min_seasons: int = 3,
    step_days: int = 7,
):
    """
    Yields (train_cutoff, test_start, test_end) triples.
    Uses a 3-season warmup, then expanding window with weekly test chunks.
    """
    seasons = con.execute("""
        SELECT DISTINCT season
        FROM fixtures WHERE league = ?
        ORDER BY season
    """, [league]).df()["season"].tolist()

    warmup_end_season = seasons[train_min_seasons - 1]
    warmup_end_date = con.execute("""
        SELECT MAX(kickoff_utc) FROM fixtures
        WHERE league = ? AND season = ?
    """, [league, warmup_end_season]).fetchone()[0]

    current = warmup_end_date
    final_date = con.execute("""
        SELECT MAX(kickoff_utc) FROM fixtures WHERE league = ?
    """, [league]).fetchone()[0]

    while current < final_date:
        test_start = current
        test_end = current + pd.Timedelta(days=step_days)
        yield (current, test_start, test_end)
        current = test_end
```

**Critical:** every feature computed inside a fold must only use data where `event_timestamp < train_cutoff`. The feature views in §6 enforce this via `:as_of`. If you build features outside the views (e.g., pandas rolling means computed on the whole dataframe), you *will* leak data.

### 7.2 Preventing data leakage (the Gemini "mid-game line movement" question)

Three concrete leakage hazards in football:

1. **Final score leak:** pretty obvious, don't include post-match fields.
2. **xG leak via same-match aggregates:** don't include the match's own xG in a feature that predicts its outcome. Use strictly prior matches.
3. **Closing line leak:** closing odds are a fantastic predictor *because they contain information about the outcome* (sharps loaded up on the winning side). Training on closing odds while testing on opening odds gives you a fake-profitable model. Either train on opening odds and test on opening odds, or explicitly model "closing line as target," not as feature.

### 7.3 Feature importance for sentiment signals specifically

Gemini asked how to tell whether a sentiment feature is adding predictive power or is noise. Three-layer check:

1. **Permutation importance vs shuffled baseline.** Permute the sentiment column in the test fold and measure drop in log-loss. If the drop is within the 95% CI of a random permutation, the feature is noise.
2. **Marginal SHAP decomposition per fold.** If SHAP mean(|value|) is positive across all 5+ seasons of walk-forward folds, the signal is stable. If it flips sign by season, it's a fit to one regime.
3. **Out-of-sample Brier score with and without.** Actually train two models — with sentiment, without — and compare calibrated Brier scores. If Brier improves by <0.002, it's not worth the pipeline complexity of maintaining the feature.

### 7.4 XGBoost vs DeepAR vs Transformer

For **pre-match markets:** XGBoost is the right answer and the literature agrees. Football match-level data has 200–400 observations per team per season, with strong domain priors (Dixon-Coles, bivariate Poisson). Deep sequence models overfit on this scale. Use XGBoost on engineered features.

For **in-play lines (not phase 1 for you):** DeepAR makes some sense because in-play odds are an autoregressive time series. But the dominant model in industry for in-play football is actually a **state-space Poisson process** with rate adjustments on game-state events (goal, red card, sub). A Transformer adds complexity without clear gain over a well-specified state-space model.

**Recommendation:** Phase 1 = XGBoost ensembled with Dixon-Coles/Skellam. Phase 3+ = consider in-play with state-space model. Skip the Transformer unless you have direct evidence it outperforms on your data.

### 7.5 Calibration with isotonic regression

Raw XGBoost outputs are not well-calibrated probabilities (they're margins fed through a sigmoid). In betting you **must** have calibrated probabilities because EV = p × (odds - 1) - (1 - p) is only meaningful if p is a true frequency.

```python
"""
Isotonic calibration on walk-forward holdout, evaluated by reliability plot
and Brier decomposition (reliability / resolution / uncertainty).
"""
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve
import numpy as np

def calibrate_and_evaluate(p_raw_train, y_train, p_raw_test, y_test):
    # Fit monotonic mapping from raw score to frequency on a held-out calibration set.
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
    iso.fit(p_raw_train, y_train)

    p_cal_test = iso.transform(p_raw_test)

    # Reliability plot data
    frac_pos, mean_pred = calibration_curve(y_test, p_cal_test, n_bins=15)

    # Brier decomposition
    brier = np.mean((p_cal_test - y_test) ** 2)

    return {
        "iso": iso,
        "p_cal_test": p_cal_test,
        "reliability_x": mean_pred,
        "reliability_y": frac_pos,
        "brier": brier,
    }
```

**Acceptance criterion:** on the reliability plot, every bin's `frac_pos` should be within ±2 percentage points of `mean_pred`. If the 60% bin actually wins 54% of the time, your "edge" is a calibration artifact and Kelly sizing will blow up your bankroll.

Use Platt scaling instead of isotonic only if your calibration set is small (<500 observations). Otherwise isotonic is strictly more flexible.

---

## Section 8 — Minimum Viable First Build (2-Week Sprint)

**Tip for free-tier operators:** before starting the sprint, drop the foundational papers into a NotebookLM notebook (free with Gemini Pro student): Dixon-Coles 1997 ("Modelling Association Football Scores and Inefficiencies in the Football Betting Market"), Karlis & Ntzoufras ("Bayesian modelling of football outcomes"), Wilkens 2026 (Bundesliga xG-Skellam paper). NotebookLM grounds answers in those papers and cites pages, which is invaluable when you're implementing the math and want to double-check formulas without burning Claude tokens on conceptual questions.

If you want to prove the thesis before investing months, here's the 2-week sprint:

**Week 1:**
- Day 1–2: Scrape football-data.co.uk for EPL + Bundesliga, 10 seasons. Load to DuckDB. Ingest Understat xG for same.
- Day 3–4: Implement Dixon-Coles (100 lines of Python with scipy.optimize). Fit per-league, estimate team attack/defense params.
- Day 5: Predict all matches in the most recent season out-of-sample using params fit on prior seasons (walk-forward).
- Day 6–7: Implement Betfair SP scraper (it's free historical data). Compute CLV for every prediction vs SP.

**Week 2:**
- Day 8: Add isotonic calibration layer on 1X2 probabilities.
- Day 9: Run paper-betting simulation with quarter-Kelly sizing. Compute ROI, Sharpe, max drawdown, CLV.
- Day 10: Plot reliability curve. If miscalibrated, investigate and fix.
- Day 11–12: Extend to Over/Under 2.5 using Skellam distribution on xG-based λ parameters.
- Day 13: Write up results: CLV distribution, ROI by season, failure cases.
- Day 14: Go/no-go decision on full project based on whether simple models already show positive CLV.

**If the MVP shows zero or negative CLV on 2000+ simulated bets, the full multi-agent architecture will not save you.** In that case the honest answer is: skip the project, or pivot to arbitrage/promo-extraction which is a different (more mechanical, less modeling-heavy) game.

**If the MVP shows positive CLV,** you have license to build the full system knowing the foundational edge is real.

---

## Section 9 — Final Warnings

1. **You will lose in your first 200 real bets with non-trivial probability.** A 5% edge means you're a 52.5% favorite per bet; 200 bets of that have about an 8% chance of ending in the red. This is not "the system doesn't work" — this is variance. Bankroll management exists for this reason.

2. **Regulators move.** Your execution stack needs to be flexible about jurisdictions. Bet365 can block your IP country tomorrow; Betfair Exchange can introduce a tier of premium charges that kills your margin (this happened in Jan 2025). Don't hard-code venue economics.

3. **The edge decays.** Every leaky data point in §3 will eventually be priced in by the market as more sharp money uses similar approaches. Plan for continuous re-discovery; don't assume today's edges are 2028's edges.

4. **This is a business, not a research project, the moment you deploy real money.** Treat bankroll as working capital, treat CLV as your P&L metric, treat the codebase as revenue-generating infrastructure. Version control, tests, monitoring, alerts, runbooks — all of it.

5. **When in doubt, don't bet.** Every bet placed out of boredom, FOMO, or "the model says 3.1% edge" (when threshold is 3%) erodes the edge. A system that places fewer, higher-conviction bets reliably beats one that places more borderline bets, even if the paper ROI looks similar.

---

## Section 10 — Future Enhancements

> **AI assistants: do not read past this heading unless the operator explicitly references future enhancements by name or section number (e.g., "§10.2" or "social signal ingestion"). This section captures brainstormed ideas to keep active design context clean. Reading it consumes tokens without action value.**

### 10.1 In-play multi-agent system

Requires a state-space Poisson model per §7.4. Deferred until the pre-match system has 60+ days of live Kalshi paper data demonstrating positive CLV. In-play on Kalshi requires sub-second price polling; infrastructure cost rises significantly. Do not design for this until pre-match is proven.

### 10.2 Social signal ingestion via Ollama on verified accounts

Per §3.1, lineup churn is a proven leaky signal. The RAG layer could be extended to monitor verified accounts (The Athletic journalists, Opta analysts, club media) for formation and injury hints. Operationally blocked by Twitter API costs (not free post-2023); alternative is RSS/web scraping of public posts which is slower and noisier. Revisit when pre-match edge is confirmed and marginal gain from social signals is measurable.

### 10.3 Active position management / hedging engine

Phase 5+ only. Requires the ability to buy and sell Kalshi contracts after initial entry. Not before 500+ real settled bets, and not before the bankroll management module has been chaos-tested against correlated market moves. The hedging logic is non-trivial: closing a position at a loss to lock in CLV is only correct if the expected future CLV on the open position is negative.

### 10.4 Multi-league expansion to La Liga, Serie A, Bundesliga, Ligue 1

The data pipeline already ingests all five leagues (football-data.co.uk + Understat). The model is trained EPL-only. Expanding to other leagues requires verifying that Kalshi lists contracts for those leagues and that liquidity is sufficient to absorb target stakes. La Liga is the next candidate (second-highest global betting volume after EPL).

### 10.5 NBA/NFL totals on Kalshi as alternative market

If EPL contract liquidity on Kalshi is thin (common for niche European fixtures), NBA/NFL totals are an alternative application of the same pipeline: over/under models, point-in-time feature snapshots, CLV vs Kalshi close. NBA season overlaps with EPL Jan–May; NFL is off-season for EPL. Could be a hedge against EPL liquidity risk without changing the architecture.
