"""Fixtures endpoints — list, detail, upcoming."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.fixtures import get_fixture, list_fixtures, list_upcoming
from footy_ev_api.auth import get_current_operator
from footy_ev_api.errors import AppError
from footy_ev_api.schemas.fixtures import (
    FixtureAliasInfo,
    FixtureDetailResponse,
    FixtureListResponse,
    FixtureResponse,
)

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


@router.get("", response_model=FixtureListResponse)
async def fixture_list(
    _operator: str = Depends(get_current_operator),
    status: str | None = Query(default=None),
    league: str | None = Query(default=None),
    season: str | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FixtureListResponse:
    """Paginated fixture list with composable filters."""
    data = list_fixtures(
        status=status,
        league=league,
        season=season,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return FixtureListResponse(
        fixtures=[FixtureResponse(**f) for f in data["fixtures"]],
        total=data["total"],
    )


@router.get("/upcoming", response_model=FixtureListResponse)
async def fixture_upcoming(
    _operator: str = Depends(get_current_operator),
    days: int = Query(default=14, ge=1, le=90),
) -> FixtureListResponse:
    """Scheduled fixtures in the next N days."""
    data = list_upcoming(days=days)
    return FixtureListResponse(
        fixtures=[FixtureResponse(**f) for f in data["fixtures"]],
        total=data["total"],
    )


@router.get("/{fixture_id}", response_model=FixtureDetailResponse)
async def fixture_detail(
    fixture_id: str,
    _operator: str = Depends(get_current_operator),
) -> FixtureDetailResponse:
    """Fixture detail with linked aliases and prediction/bet counts."""
    data = get_fixture(fixture_id)
    if data is None:
        raise AppError("FIXTURE_NOT_FOUND", f"Fixture {fixture_id} not found", 404)
    aliases_raw = data.pop("aliases", [])
    return FixtureDetailResponse(
        **data,
        aliases=[FixtureAliasInfo(**a) for a in aliases_raw],
    )
