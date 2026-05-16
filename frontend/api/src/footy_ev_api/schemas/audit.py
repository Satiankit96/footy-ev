"""Pydantic schemas for audit endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class OperatorActionRow(BaseModel):
    action_id: str
    action_type: str
    operator: str
    performed_at: str
    input_params: str | None = None
    result_summary: str | None = None
    request_id: str | None = None


class OperatorActionsResponse(BaseModel):
    actions: list[OperatorActionRow]
    total: int


class ModelVersionRow(BaseModel):
    model_version: str
    first_seen: str | None = None
    last_seen: str | None = None
    prediction_count: int


class ModelVersionsResponse(BaseModel):
    versions: list[ModelVersionRow]


class DecisionRow(BaseModel):
    bet_id: str
    fixture_id: str
    decided_at: str | None = None
    market: str
    selection: str
    stake_gbp: str
    odds: str
    edge_pct: float | None = None
    settlement_status: str
    prediction_id: str | None = None


class DecisionsResponse(BaseModel):
    decisions: list[DecisionRow]
    total: int
