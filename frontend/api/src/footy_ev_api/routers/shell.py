"""Shell data endpoint: everything the app shell needs in one call."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from footy_ev_api.auth import get_current_operator, get_kalshi_base_url
from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.schemas.shell import (
    CircuitBreakerInfo,
    PipelineInfo,
    ShellResponse,
    VenueInfo,
)

router = APIRouter(tags=["shell"])


@router.get("/shell", response_model=ShellResponse)
async def shell(
    _operator: str = Depends(get_current_operator),
) -> ShellResponse:
    """Return venue, circuit breaker, and pipeline state for the app shell."""
    base_url = get_kalshi_base_url()
    if base_url:
        venue = VenueInfo(
            name="kalshi",
            base_url=base_url,
            is_demo="demo" in base_url.lower(),
        )
    else:
        venue = VenueInfo(name="not configured", base_url="", is_demo=False)

    mgr = JobManager()

    return ShellResponse(
        operator="operator",
        venue=venue,
        circuit_breaker=CircuitBreakerInfo(
            state="ok",
            last_tripped_at=None,
            reason=None,
        ),
        pipeline=PipelineInfo(
            loop_active=mgr.loop_active,
            last_cycle_at=mgr.loop_state.get("last_cycle_at"),
        ),
    )
