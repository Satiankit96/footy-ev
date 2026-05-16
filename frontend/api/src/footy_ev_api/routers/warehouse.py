"""Warehouse explorer router — /api/v1/warehouse/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.warehouse import (
    get_team,
    list_players,
    list_snapshots,
    list_tables,
    list_teams,
    run_canned_query,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.queries.registry import list_query_names
from footy_ev_api.schemas.warehouse import (
    CannedQueryRequest,
    CannedQueryResponse,
    PlayerListResponse,
    SnapshotListResponse,
    TableListResponse,
    TeamDetailResponse,
    TeamListResponse,
)

router = APIRouter(tags=["warehouse"])

_AUTH = [Depends(get_current_operator)]


@router.get(
    "/warehouse/tables",
    response_model=TableListResponse,
    dependencies=_AUTH,
)
def route_list_tables() -> TableListResponse:
    """All user BASE TABLEs with row counts and last-write timestamps."""
    return TableListResponse(**list_tables())


@router.get(
    "/warehouse/teams",
    response_model=TeamListResponse,
    dependencies=_AUTH,
)
def route_list_teams(
    league: str | None = Query(default=None, description="Filter by league name"),
) -> TeamListResponse:
    """Teams derived from fixture history, optionally filtered by league."""
    return TeamListResponse(**list_teams(league=league))


@router.get(
    "/warehouse/teams/{team_id}",
    response_model=TeamDetailResponse,
    dependencies=_AUTH,
)
def route_get_team(team_id: str) -> TeamDetailResponse:
    """Team detail with last-5 form."""
    result = get_team(team_id)
    if result is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Team '{team_id}' not found")
    return TeamDetailResponse(**result)


@router.get(
    "/warehouse/players",
    response_model=PlayerListResponse,
    dependencies=_AUTH,
)
def route_list_players(
    team_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PlayerListResponse:
    """Player list (currently empty — no players table in schema)."""
    return PlayerListResponse(**list_players(team_id=team_id, limit=limit, offset=offset))


@router.get(
    "/warehouse/odds-snapshots",
    response_model=SnapshotListResponse,
    dependencies=_AUTH,
)
def route_list_snapshots(
    fixture_id: str | None = Query(default=None),
    market: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SnapshotListResponse:
    """Paginated odds-snapshot browser with composable filters."""
    return SnapshotListResponse(
        **list_snapshots(
            fixture_id=fixture_id,
            market=market,
            venue=venue,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/warehouse/query/names",
    response_model=list[str],
    dependencies=_AUTH,
)
def route_list_query_names() -> list[str]:
    """List all allowed canned-query names."""
    return list_query_names()


@router.post(
    "/warehouse/query",
    response_model=CannedQueryResponse,
    dependencies=_AUTH,
)
def route_run_query(body: CannedQueryRequest) -> CannedQueryResponse:
    """Execute a named query from the allowlist. Rejects unknown query names."""
    result = run_canned_query(body.query_name, body.params)
    return CannedQueryResponse(**result)
