"""Health endpoint response schema."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """GET /api/v1/health response."""

    status: str
    version: str
    uptime_s: float
    active_venue: str | None = None
