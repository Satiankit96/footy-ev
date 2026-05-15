"""Pydantic schemas for paper bets endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BetResponse(BaseModel):
    decision_id: str
    fixture_id: str
    market: str
    selection: str
    odds_at_decision: float
    stake_gbp: str  # Decimal as string
    edge_pct: float
    kelly_fraction_used: float
    settlement_status: str
    clv_pct: float | None
    decided_at: str | None
    venue: str


class BetListResponse(BaseModel):
    bets: list[BetResponse]
    total: int


class KellyBreakdown(BaseModel):
    p_hat: float
    sigma_p: float
    uncertainty_k: float
    p_lb: float
    b: float
    q: float
    f_full: float
    base_fraction: float
    per_bet_cap_pct: float
    f_used: float
    per_bet_cap_hit: bool
    bankroll_used: str  # Decimal as string


class EdgeMath(BaseModel):
    p_calibrated: float
    odds_decimal: float
    commission: float
    edge: float
    edge_pct_stored: float


class BetDetailResponse(BetResponse):
    run_id: str | None
    sigma_p: float | None
    bankroll_used: str  # Decimal as string
    features_hash: str
    settled_at: str | None
    pnl_gbp: str | None  # Decimal as string
    closing_odds: float | None
    kelly_breakdown: KellyBreakdown
    edge_math: EdgeMath


class BetsSummaryResponse(BaseModel):
    period: str
    total_bets: int
    wins: int
    losses: int
    pending: int
    total_pnl: str  # Decimal as string
    total_staked: str  # Decimal as string
    roi: float
    mean_clv: float | None
    min_clv: float | None
    max_clv: float | None


class ClvRollingPoint(BaseModel):
    bet_index: int
    decided_at: str
    clv_pct: float
    rolling_clv: float
    cumulative_clv: float


# Used by both bets/clv/rolling and clv/rolling
ClvRollingResponse = list[ClvRollingPoint]


class ClvBreakdownItem(BaseModel):
    fixture_id: str
    market: str
    selection: str
    mean_clv: float | None
    n_bets: int
    total_staked: str
    total_pnl: str


class ClvSourceItem(BaseModel):
    source: str
    n_bets: int
    mean_clv: float | None


class ClvBackfillRequest(BaseModel):
    from_date: str | None = None
    to_date: str | None = None


class ClvBackfillResponse(BaseModel):
    job_id: str
    status: str


class BetHistogramBin(BaseModel):
    bin_center: float
    count: int


# Re-export for convenience
__all__: list[Any] = [
    "BetResponse",
    "BetListResponse",
    "KellyBreakdown",
    "EdgeMath",
    "BetDetailResponse",
    "BetsSummaryResponse",
    "ClvRollingPoint",
    "ClvRollingResponse",
    "ClvBreakdownItem",
    "ClvSourceItem",
    "ClvBackfillRequest",
    "ClvBackfillResponse",
    "BetHistogramBin",
]
