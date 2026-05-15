"""Paper bets router — /api/v1/bets/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from footy_ev_api.adapters.bets import (
    get_bet,
    get_bets_summary,
    list_bets,
)
from footy_ev_api.adapters.clv import get_clv_rolling
from footy_ev_api.auth import get_current_operator
from footy_ev_api.errors import AppError
from footy_ev_api.schemas.bets import (
    BetDetailResponse,
    BetListResponse,
    BetsSummaryResponse,
    ClvRollingPoint,
)

router = APIRouter(tags=["bets"])


@router.get("/bets", response_model=BetListResponse, dependencies=[Depends(get_current_operator)])
def route_list_bets(
    status: str | None = None,
    fixture_id: str | None = None,
    venue: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> BetListResponse:
    """Paginated paper bets ledger."""
    data = list_bets(
        status=status,
        fixture_id=fixture_id,
        venue=venue,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return BetListResponse(**data)


@router.get(
    "/bets/summary",
    response_model=BetsSummaryResponse,
    dependencies=[Depends(get_current_operator)],
)
def route_bets_summary(
    period: str = Query("all", pattern="^(7d|30d|all)$"),
) -> BetsSummaryResponse:
    """Aggregate bets stats."""
    return BetsSummaryResponse(**get_bets_summary(period))


@router.get(
    "/bets/clv/rolling",
    response_model=list[ClvRollingPoint],
    dependencies=[Depends(get_current_operator)],
)
def route_bets_clv_rolling(
    window: int = Query(100, ge=1, le=500),
) -> list[ClvRollingPoint]:
    """Rolling CLV time series — delegates to the CLV adapter (single source)."""
    return [ClvRollingPoint(**r) for r in get_clv_rolling(window=window)]


@router.get(
    "/bets/{decision_id}",
    response_model=BetDetailResponse,
    dependencies=[Depends(get_current_operator)],
)
def route_bet_detail(decision_id: str) -> BetDetailResponse:
    """Full bet audit detail with Kelly breakdown."""
    try:
        data = get_bet(decision_id)
    except Exception as exc:
        raise AppError("BET_QUERY_ERROR", str(exc), 500) from exc

    if data is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "BET_NOT_FOUND"}})
    return BetDetailResponse(**data)
