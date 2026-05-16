"""Schemas for live-trading gate endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ClvConditionResult(BaseModel):
    met: bool
    bet_count: int
    days_span: int
    mean_clv_pct: float


class BankrollConditionResult(BaseModel):
    met: bool
    flag_name: str
    flag_set: bool


class ConditionsResponse(BaseModel):
    clv_condition: ClvConditionResult
    bankroll_condition: BankrollConditionResult
    all_met: bool


class LiveTradingStatus(BaseModel):
    enabled: bool
    gate_reasons: list[str]
