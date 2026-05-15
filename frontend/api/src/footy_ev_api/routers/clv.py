"""CLV analytics router — /api/v1/clv/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.clv import (
    get_clv_breakdown,
    get_clv_rolling,
    get_clv_sources,
    run_clv_backfill,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.schemas.bets import (
    ClvBackfillRequest,
    ClvBackfillResponse,
    ClvBreakdownItem,
    ClvRollingPoint,
    ClvSourceItem,
)

router = APIRouter(tags=["clv"])


@router.get(
    "/clv/rolling",
    response_model=list[ClvRollingPoint],
    dependencies=[Depends(get_current_operator)],
)
def route_clv_rolling(
    window: int = Query(100, ge=1, le=500),
    since: str | None = None,
) -> list[ClvRollingPoint]:
    """Rolling N-bet CLV time series."""
    return [ClvRollingPoint(**r) for r in get_clv_rolling(window=window, since=since)]


@router.get(
    "/clv/breakdown",
    response_model=list[ClvBreakdownItem],
    dependencies=[Depends(get_current_operator)],
)
def route_clv_breakdown(
    fixture_id: str | None = None,
) -> list[ClvBreakdownItem]:
    """Per-fixture CLV decomposition."""
    return [ClvBreakdownItem(**r) for r in get_clv_breakdown(fixture_id)]


@router.get(
    "/clv/sources",
    response_model=list[ClvSourceItem],
    dependencies=[Depends(get_current_operator)],
)
def route_clv_sources() -> list[ClvSourceItem]:
    """CLV benchmark source counts (kalshi close / pinnacle / missing)."""
    return [ClvSourceItem(**r) for r in get_clv_sources()]


@router.post(
    "/clv/backfill",
    response_model=ClvBackfillResponse,
    dependencies=[Depends(get_current_operator)],
)
def route_clv_backfill(body: ClvBackfillRequest) -> ClvBackfillResponse:
    """Kick off CLV backfill job via JobManager."""
    mgr = JobManager()

    def run_fn(job: object, broadcast: object) -> None:
        run_clv_backfill(
            job,  # type: ignore[arg-type]
            broadcast,
            from_date=body.from_date,
            to_date=body.to_date,
        )

    job = mgr.start_job("clv_backfill", run_fn)
    return ClvBackfillResponse(job_id=job.job_id, status=job.status.value)
