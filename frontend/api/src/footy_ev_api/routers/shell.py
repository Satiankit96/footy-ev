"""Shell data endpoint: everything the app shell needs in one call."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from footy_ev_api.auth import get_current_operator, get_kalshi_base_url

router = APIRouter(tags=["shell"])


@router.get("/shell")
async def shell(
    _operator: str = Depends(get_current_operator),
) -> dict[str, Any]:
    """Return venue, circuit breaker, and pipeline state for the app shell."""
    base_url = get_kalshi_base_url()
    if base_url:
        venue: dict[str, Any] = {
            "name": "kalshi",
            "base_url": base_url,
            "is_demo": "demo" in base_url.lower(),
        }
    else:
        venue = {"name": "not configured", "base_url": "", "is_demo": False}

    return {
        "operator": "operator",
        "venue": venue,
        "circuit_breaker": {
            "state": "ok",
            "last_tripped_at": None,
            "reason": None,
        },
        "pipeline": {
            "loop_active": False,
            "last_cycle_at": None,
        },
    }
