"""Shell endpoint response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class VenueInfo(BaseModel):
    """Venue configuration state."""

    name: str
    base_url: str
    is_demo: bool


class CircuitBreakerInfo(BaseModel):
    """Circuit breaker state."""

    state: str
    last_tripped_at: str | None
    reason: str | None


class PipelineInfo(BaseModel):
    """Pipeline loop state."""

    loop_active: bool
    last_cycle_at: str | None


class ShellResponse(BaseModel):
    """GET /api/v1/shell response."""

    operator: str
    venue: VenueInfo
    circuit_breaker: CircuitBreakerInfo
    pipeline: PipelineInfo
