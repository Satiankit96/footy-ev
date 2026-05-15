"""Pydantic schemas for risk endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ExposureFixture(BaseModel):
    fixture_id: str
    open_stake: str  # Decimal as string


class ExposureResponse(BaseModel):
    today_open: str  # sum of pending stakes decided today
    total_open: str  # sum of all pending stakes
    per_fixture: list[ExposureFixture]


class BankrollPoint(BaseModel):
    decided_at: str
    bankroll: str  # Decimal as string


class BankrollResponse(BaseModel):
    current: str  # Decimal as string
    peak: str  # Decimal as string
    drawdown_pct: float  # fraction, e.g. 0.12 = 12%
    sparkline: list[BankrollPoint]


class KellyPreviewRequest(BaseModel):
    p_hat: float
    sigma_p: float
    odds: float
    base_fraction: float = 0.25
    uncertainty_k: float = 1.0
    per_bet_cap_pct: float = 0.02
    recent_clv_pct: float = 0.0
    bankroll: str = "1000"  # Decimal as string


class KellyPreviewResponse(BaseModel):
    stake: str  # Decimal as string
    f_full: float
    f_used: float
    p_lb: float
    clv_multiplier: float
    per_bet_cap_hit: bool
