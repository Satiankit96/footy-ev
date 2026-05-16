"""Pydantic schemas for warehouse explorer endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TableInfo(BaseModel):
    name: str
    row_count: int
    last_write: str | None = None


class TableListResponse(BaseModel):
    tables: list[TableInfo]


class TeamRow(BaseModel):
    team_id: str
    name: str | None = None
    league: str | None = None
    fixture_count: int


class TeamListResponse(BaseModel):
    teams: list[TeamRow]
    total: int


class FormResult(BaseModel):
    fixture_id: str
    date: str | None = None
    opponent_id: str
    home_away: str
    score: str | None = None
    result: str | None = None
    home_xg: str | None = None
    away_xg: str | None = None


class TeamDetailResponse(BaseModel):
    team_id: str
    name: str | None = None
    league: str | None = None
    form: list[FormResult]


class PlayerListResponse(BaseModel):
    players: list[Any]
    note: str


class SnapshotRow(BaseModel):
    fixture_id: str
    venue: str
    market: str
    selection: str
    odds_decimal: float | None = None
    received_at: str | None = None


class SnapshotListResponse(BaseModel):
    snapshots: list[SnapshotRow]
    total: int


class CannedQueryRequest(BaseModel):
    query_name: str
    params: dict[str, Any] = {}


class CannedQueryResponse(BaseModel):
    query_name: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
