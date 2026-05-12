"""LangGraph state schema + Pydantic domain types (BLUE_MAP s2.3).

The graph state is a TypedDict with reducers — list fields use
`Annotated[list[T], add]` so parallel scraper+news fan-in concatenates
their outputs at the analyst node instead of overwriting each other.

Domain types (OddsSnapshot, ModelProbability, BetDecision) are pydantic
v2 models so they validate at the seam between adapter code (which
returns dicts) and the graph (which expects typed records).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from operator import add
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field


class MarketType(str, Enum):
    MATCH_1X2 = "1x2"
    OU_25 = "ou_2.5"
    BTTS = "btts"
    ASIAN_HCP = "asian_handicap"


class OddsSnapshot(BaseModel):
    venue: str
    fixture_id: str
    market: MarketType
    selection: str
    odds_decimal: float
    captured_at: datetime
    source_timestamp: datetime | None = None
    staleness_seconds: int = 0
    liquidity_gbp: float | None = None


class ModelProbability(BaseModel):
    fixture_id: str
    market: MarketType
    selection: str
    p_raw: float
    p_calibrated: float
    model_version: str
    features_hash: str
    uncertainty_se: float
    run_id: str | None = None  # backtest_runs.run_id that produced the calibration


class BetDecision(BaseModel):
    fixture_id: str
    market: MarketType
    selection: str
    odds_at_decision: float
    p_calibrated: float
    sigma_p: float | None = None
    edge_pct: float
    kelly_fraction_used: float
    stake_gbp: Decimal
    bankroll_used: Decimal
    venue: str
    decided_at: datetime
    features_hash: str
    rationale: str = ""
    run_id: str | None = None
    portfolio_cap_hit: bool = False
    per_bet_cap_hit: bool = False


class BettingState(TypedDict, total=False):
    """LangGraph state passed between nodes.

    All fields are optional because the graph runs partial state on each
    tick. List fields use the `add` reducer so parallel branches
    concatenate.
    """

    fixtures_to_process: list[str]
    as_of: datetime

    # Populated by the scraper after Kalshi event tickers are resolved to
    # warehouse fixture_ids via kalshi_event_aliases. The analyst uses
    # this list for scoring.
    resolved_fixture_ids: list[str]

    odds_snapshots: Annotated[list[OddsSnapshot], add]
    news_deltas: Annotated[list[dict[str, Any]], add]
    model_probs: Annotated[list[ModelProbability], add]

    candidate_bets: list[BetDecision]
    placed_bets: list[BetDecision]

    circuit_breaker_tripped: bool
    breaker_reason: str
    data_freshness_seconds: dict[str, int]
    last_error: str | None

    # Operator inputs threaded through the graph
    bankroll_gbp: float
    edge_threshold_pct: float
    invocation_id: str


class CircuitBreakerEvent(BaseModel):
    """Recorded to circuit_breaker_log when a node trips the breaker."""

    event_id: str = Field(..., description="hash(reason+source+tripped_at)")
    tripped_at: datetime
    reason: str
    affected_source: str
    max_staleness_sec: int | None = None
