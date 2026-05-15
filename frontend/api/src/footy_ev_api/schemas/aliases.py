"""Alias endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel


class AliasResponse(BaseModel):
    """Single alias record."""

    event_ticker: str
    fixture_id: str
    confidence: float
    resolved_by: str
    resolved_at: str | None = None
    status: str = "active"


class AliasListResponse(BaseModel):
    """GET /api/v1/aliases response."""

    aliases: list[AliasResponse]
    total: int


class AliasCreateRequest(BaseModel):
    """POST /api/v1/aliases body."""

    event_ticker: str
    fixture_id: str
    confidence: float = 1.0
    resolved_by: str = "manual"


class AliasRetireResponse(BaseModel):
    """POST /api/v1/aliases/{ticker}/retire response."""

    event_ticker: str
    status: str
    retired_at: str


class AliasConflict(BaseModel):
    """A fixture with multiple active aliases."""

    fixture_id: str
    alias_count: int
    tickers: list[str]


class AliasConflictsResponse(BaseModel):
    """GET /api/v1/aliases/conflicts response."""

    conflicts: list[AliasConflict]
