"""Bootstrap endpoints — run, preview, job history."""

from __future__ import annotations

import functools

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.bootstrap import preview_bootstrap, run_bootstrap
from footy_ev_api.auth import get_current_operator
from footy_ev_api.errors import AppError
from footy_ev_api.jobs.manager import Job, JobManager
from footy_ev_api.schemas.bootstrap import (
    BootstrapJobListResponse,
    BootstrapJobResponse,
    BootstrapPreviewResponse,
    BootstrapRunRequest,
    BootstrapRunResponse,
)

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


def _job_to_response(j: Job) -> BootstrapJobResponse:
    return BootstrapJobResponse(
        job_id=j.job_id,
        job_type=j.job_type,
        status=j.status.value,
        started_at=j.started_at.isoformat() if j.started_at else None,
        completed_at=j.completed_at.isoformat() if j.completed_at else None,
        error=j.error,
        progress=j.progress,
    )


@router.post("/run", response_model=BootstrapRunResponse)
async def bootstrap_run(
    body: BootstrapRunRequest,
    _operator: str = Depends(get_current_operator),
) -> BootstrapRunResponse:
    """Start a bootstrap job. Returns job_id for WS progress tracking."""
    mgr = JobManager()
    run_fn = functools.partial(
        run_bootstrap,
        mode=body.mode,
        create_fixtures=body.create_fixtures,
        fixture_path=body.fixture_path,
    )
    try:
        job = mgr.start_job("bootstrap", run_fn)
    except ValueError as exc:
        raise AppError("CONFLICT", str(exc), 409) from exc
    return BootstrapRunResponse(job_id=job.job_id, status=job.status.value)


@router.get("/preview", response_model=BootstrapPreviewResponse)
async def bootstrap_preview(
    _operator: str = Depends(get_current_operator),
    mode: str = Query(default="live"),
    fixture_path: str | None = Query(default=None),
) -> BootstrapPreviewResponse:
    """Dry-run: returns what bootstrap would do, zero warehouse writes."""
    data = preview_bootstrap(mode=mode, fixture_path=fixture_path)
    return BootstrapPreviewResponse(**data)


@router.get("/jobs", response_model=BootstrapJobListResponse)
async def bootstrap_jobs(
    _operator: str = Depends(get_current_operator),
    limit: int = Query(default=20, ge=1, le=100),
) -> BootstrapJobListResponse:
    """List bootstrap job history."""
    mgr = JobManager()
    all_jobs = mgr.get_jobs(limit=limit)
    bootstrap_only = [j for j in all_jobs if j.job_type == "bootstrap"]
    return BootstrapJobListResponse(jobs=[_job_to_response(j) for j in bootstrap_only])


@router.get("/jobs/{job_id}", response_model=BootstrapJobResponse)
async def bootstrap_job_detail(
    job_id: str,
    _operator: str = Depends(get_current_operator),
) -> BootstrapJobResponse:
    """Get bootstrap job detail."""
    mgr = JobManager()
    job = mgr.get_job(job_id)
    if job is None or job.job_type != "bootstrap":
        raise AppError("JOB_NOT_FOUND", f"Bootstrap job {job_id} not found", 404)
    return _job_to_response(job)
