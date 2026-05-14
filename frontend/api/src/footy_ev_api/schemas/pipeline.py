"""Pipeline endpoint request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel

from footy_ev_api.schemas.shell import CircuitBreakerInfo


class FreshnessEntry(BaseModel):
    """Per-source freshness gauge."""

    source: str
    last_seen_at: str | None
    age_seconds: int | None
    threshold_seconds: int
    status: str  # "ok" | "warning" | "stale"


class LoopStateResponse(BaseModel):
    """Pipeline polling loop state."""

    active: bool
    interval_min: int | None
    started_at: str | None
    last_cycle_at: str | None
    cycles_completed: int


class PipelineStatusResponse(BaseModel):
    """GET /api/v1/pipeline/status response."""

    last_cycle_at: str | None
    last_cycle_duration_s: float | None
    circuit_breaker: CircuitBreakerInfo
    loop: LoopStateResponse
    freshness: dict[str, FreshnessEntry]


class StartCycleResponse(BaseModel):
    """POST /api/v1/pipeline/cycle response."""

    job_id: str
    status: str


class StartLoopRequest(BaseModel):
    """POST /api/v1/pipeline/loop/start request body."""

    interval_min: int


class StartLoopResponse(BaseModel):
    """POST /api/v1/pipeline/loop/start response."""

    loop_id: str
    interval_min: int


class StopLoopResponse(BaseModel):
    """POST /api/v1/pipeline/loop/stop response."""

    ok: bool


class JobResponse(BaseModel):
    """Single job detail."""

    job_id: str
    job_type: str
    status: str
    started_at: str | None
    completed_at: str | None
    duration_s: float | None
    error: str | None
    progress: list[dict[str, object]]


class JobListResponse(BaseModel):
    """GET /api/v1/pipeline/jobs response."""

    jobs: list[JobResponse]
