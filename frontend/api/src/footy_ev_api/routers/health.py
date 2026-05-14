"""Health-check endpoint."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter

from footy_ev_api.schemas.health import HealthResponse

router = APIRouter(tags=["health"])
_started_at = datetime.now(UTC)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe. No auth required."""
    uptime = (datetime.now(UTC) - _started_at).total_seconds()
    venue_url = os.environ.get("KALSHI_API_BASE_URL", "")
    return HealthResponse(
        status="ok",
        version="0.1.0",
        uptime_s=round(uptime, 1),
        active_venue=venue_url or None,
    )
