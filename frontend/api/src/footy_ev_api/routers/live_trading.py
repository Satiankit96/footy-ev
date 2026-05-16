"""Live-trading gate router — /api/v1/live-trading/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from footy_ev_api.adapters.live_trading import check_conditions, get_live_trading_status
from footy_ev_api.auth import get_current_operator
from footy_ev_api.schemas.live_trading import ConditionsResponse, LiveTradingStatus

router = APIRouter(tags=["live-trading"])

_AUTH = [Depends(get_current_operator)]

_405_BODY = {
    "error": {
        "code": "METHOD_NOT_ALLOWED",
        "message": "Enabling live trading via the API is not permitted. "
        "Edit .env directly after both gate conditions are met.",
    }
}


@router.get(
    "/live-trading/status",
    response_model=LiveTradingStatus,
    dependencies=_AUTH,
)
def route_live_trading_status() -> LiveTradingStatus:
    """Gate status. enabled is always False — UI never acknowledges live mode."""
    return LiveTradingStatus(**get_live_trading_status())


@router.post(
    "/live-trading/check-conditions",
    response_model=ConditionsResponse,
    dependencies=_AUTH,
)
def route_check_conditions() -> ConditionsResponse:
    """Run §3 bankroll-discipline gate checks against the warehouse. Read-only."""
    data = check_conditions()
    return ConditionsResponse(
        clv_condition=data["clv_condition"],
        bankroll_condition=data["bankroll_condition"],
        all_met=data["all_met"],
    )


@router.post("/live-trading/enable", include_in_schema=False)
@router.put("/live-trading/enable", include_in_schema=False)
def route_enable_not_allowed() -> JSONResponse:
    """Intentionally absent — returns 405 to any enable attempt."""
    return JSONResponse(status_code=405, content=_405_BODY)
