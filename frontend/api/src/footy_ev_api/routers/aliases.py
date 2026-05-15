"""Alias management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.aliases import (
    create_alias,
    get_alias,
    get_conflicts,
    list_aliases,
    retire_alias,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.errors import AppError
from footy_ev_api.schemas.aliases import (
    AliasConflict,
    AliasConflictsResponse,
    AliasCreateRequest,
    AliasListResponse,
    AliasResponse,
    AliasRetireResponse,
)

router = APIRouter(prefix="/aliases", tags=["aliases"])


@router.get("", response_model=AliasListResponse)
async def alias_list(
    _operator: str = Depends(get_current_operator),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AliasListResponse:
    """List Kalshi event aliases."""
    data = list_aliases(status=status, limit=limit, offset=offset)
    return AliasListResponse(
        aliases=[AliasResponse(**a) for a in data["aliases"]],
        total=data["total"],
    )


@router.get("/conflicts", response_model=AliasConflictsResponse)
async def alias_conflicts(
    _operator: str = Depends(get_current_operator),
) -> AliasConflictsResponse:
    """Find aliases pointing at the same fixture."""
    conflicts = get_conflicts()
    return AliasConflictsResponse(
        conflicts=[AliasConflict(**c) for c in conflicts],
    )


@router.get("/{event_ticker}", response_model=AliasResponse)
async def alias_detail(
    event_ticker: str,
    _operator: str = Depends(get_current_operator),
) -> AliasResponse:
    """Get a single alias by event ticker."""
    alias = get_alias(event_ticker)
    if alias is None:
        raise AppError("ALIAS_NOT_FOUND", f"No alias found for {event_ticker}", 404)
    return AliasResponse(**alias)


@router.post("", response_model=AliasResponse)
async def alias_create(
    body: AliasCreateRequest,
    _operator: str = Depends(get_current_operator),
) -> AliasResponse:
    """Manually create an alias. Validates fixture exists."""
    data = create_alias(
        event_ticker=body.event_ticker,
        fixture_id=body.fixture_id,
        confidence=body.confidence,
        resolved_by=body.resolved_by,
    )
    return AliasResponse(**data)


@router.post("/{event_ticker}/retire", response_model=AliasRetireResponse)
async def alias_retire(
    event_ticker: str,
    _operator: str = Depends(get_current_operator),
) -> AliasRetireResponse:
    """Retire an alias (append-only — never deletes)."""
    data = retire_alias(event_ticker)
    return AliasRetireResponse(**data)
