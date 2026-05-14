"""Health-check endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])
_started_at = datetime.now(UTC)


@router.get("/health")
async def health() -> dict[str, object]:
    """Liveness probe. No auth required."""
    uptime = (datetime.now(UTC) - _started_at).total_seconds()
    return {"status": "ok", "version": "0.1.0", "uptime_s": round(uptime, 1)}
