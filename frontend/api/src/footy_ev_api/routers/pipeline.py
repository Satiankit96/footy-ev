"""Pipeline control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.pipeline import run_pipeline_cycle
from footy_ev_api.auth import get_current_operator
from footy_ev_api.errors import AppError
from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.schemas.pipeline import (
    FreshnessEntry,
    JobListResponse,
    JobResponse,
    LoopStateResponse,
    PipelineStatusResponse,
    StartCycleResponse,
    StartLoopRequest,
    StartLoopResponse,
    StopLoopResponse,
)
from footy_ev_api.schemas.shell import CircuitBreakerInfo

router = APIRouter(tags=["pipeline"])

_FRESHNESS_SOURCES: dict[str, int] = {
    "kalshi_events": 600,
    "kalshi_markets": 600,
    "understat": 86400,
    "fbref": 86400,
    "football_data": 86400,
}


def _job_to_response(j: object) -> JobResponse:
    from footy_ev_api.jobs.manager import Job

    job: Job = j  # type: ignore[assignment]
    duration: float | None = None
    if job.started_at and job.completed_at:
        duration = round((job.completed_at - job.started_at).total_seconds(), 2)
    return JobResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status.value,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_s=duration,
        error=job.error,
        progress=job.progress,
    )


def _freshness_stub() -> dict[str, FreshnessEntry]:
    entries: dict[str, FreshnessEntry] = {}
    for src, threshold in _FRESHNESS_SOURCES.items():
        entries[src] = FreshnessEntry(
            source=src,
            last_seen_at=None,
            age_seconds=None,
            threshold_seconds=threshold,
            status="stale",
        )
    return entries


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
async def pipeline_status(
    _op: str = Depends(get_current_operator),
) -> PipelineStatusResponse:
    """Current pipeline state: last cycle, breaker, freshness."""
    mgr = JobManager()
    loop = mgr.loop_state
    last_job = next(
        (j for j in mgr.get_jobs(limit=1) if j.job_type == "pipeline_cycle"),
        None,
    )
    last_at: str | None = None
    last_dur: float | None = None
    if last_job and last_job.completed_at:
        last_at = last_job.completed_at.isoformat()
        if last_job.started_at:
            last_dur = round(
                (last_job.completed_at - last_job.started_at).total_seconds(),
                2,
            )
    return PipelineStatusResponse(
        last_cycle_at=last_at,
        last_cycle_duration_s=last_dur,
        circuit_breaker=CircuitBreakerInfo(state="ok", last_tripped_at=None, reason=None),
        loop=LoopStateResponse(**loop),
        freshness=_freshness_stub(),
    )


@router.post("/pipeline/cycle", response_model=StartCycleResponse)
async def start_cycle(
    _op: str = Depends(get_current_operator),
) -> StartCycleResponse:
    """Start one pipeline cycle. 409 if already running."""
    mgr = JobManager()
    try:
        job = mgr.start_cycle(run_pipeline_cycle)
    except ValueError as exc:
        raise AppError("CONFLICT", str(exc), 409) from exc
    return StartCycleResponse(job_id=job.job_id, status=job.status.value)


@router.post("/pipeline/loop/start", response_model=StartLoopResponse)
async def start_loop(
    body: StartLoopRequest,
    _op: str = Depends(get_current_operator),
) -> StartLoopResponse:
    """Start the polling loop. 409 if already active."""
    mgr = JobManager()
    try:
        result = mgr.start_loop(body.interval_min, run_pipeline_cycle)
    except ValueError as exc:
        raise AppError("CONFLICT", str(exc), 409) from exc
    return StartLoopResponse(**result)


@router.post("/pipeline/loop/stop", response_model=StopLoopResponse)
async def stop_loop(
    _op: str = Depends(get_current_operator),
) -> StopLoopResponse:
    """Stop the polling loop. Idempotent."""
    mgr = JobManager()
    mgr.stop_loop()
    return StopLoopResponse(ok=True)


@router.get("/pipeline/loop", response_model=LoopStateResponse)
async def loop_state(
    _op: str = Depends(get_current_operator),
) -> LoopStateResponse:
    """Current loop state."""
    mgr = JobManager()
    return LoopStateResponse(**mgr.loop_state)


@router.get("/pipeline/freshness", response_model=dict[str, FreshnessEntry])
async def freshness(
    _op: str = Depends(get_current_operator),
) -> dict[str, FreshnessEntry]:
    """Per-source freshness gauges."""
    return _freshness_stub()


@router.get("/pipeline/jobs", response_model=JobListResponse)
async def list_jobs(
    _op: str = Depends(get_current_operator),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> JobListResponse:
    """List recent jobs."""
    mgr = JobManager()
    jobs = mgr.get_jobs(status=status, limit=limit)
    return JobListResponse(jobs=[_job_to_response(j) for j in jobs])


@router.get("/pipeline/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    _op: str = Depends(get_current_operator),
) -> JobResponse:
    """Single job detail."""
    mgr = JobManager()
    job = mgr.get_job(job_id)
    if not job:
        raise AppError("NOT_FOUND", f"Job {job_id} not found", 404)
    return _job_to_response(job)
