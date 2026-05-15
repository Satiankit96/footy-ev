"""Bootstrap endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel


class BootstrapRunRequest(BaseModel):
    """POST /api/v1/bootstrap/run body."""

    mode: str = "live"
    create_fixtures: bool = True
    fixture_path: str | None = None


class BootstrapRunResponse(BaseModel):
    """POST /api/v1/bootstrap/run response."""

    job_id: str
    status: str


class BootstrapPreviewResponse(BaseModel):
    """GET /api/v1/bootstrap/preview response."""

    total_events: int
    already_mapped: int
    would_resolve: int
    would_create_fixture: int
    would_skip: int


class BootstrapJobResponse(BaseModel):
    """Single bootstrap job record."""

    job_id: str
    job_type: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    progress: list[dict[str, object]]


class BootstrapJobListResponse(BaseModel):
    """GET /api/v1/bootstrap/jobs response."""

    jobs: list[BootstrapJobResponse]
