"""In-process job tracker for background pipeline tasks."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class JobStatus(Enum):
    """Lifecycle states for a tracked job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """A tracked background job."""

    job_id: str
    job_type: str
    status: JobStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    progress: list[dict[str, Any]] = field(default_factory=list)


class JobManager:
    """Singleton tracker for background tasks.

    Keeps up to 50 recent jobs in memory. Serialises mutating jobs
    so only one pipeline_cycle or bootstrap runs at a time.
    """

    _instance: JobManager | None = None
    _MAX_JOBS = 50

    def __new__(cls) -> JobManager:
        """Ensure singleton."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._jobs: deque[Job] = deque(maxlen=self._MAX_JOBS)
        self._lock = threading.Lock()
        self._active_job_id: str | None = None
        self._loop_thread: threading.Thread | None = None
        self._loop_stop: threading.Event = threading.Event()
        self._loop_interval_min: int | None = None
        self._loop_started_at: datetime | None = None
        self._loop_last_cycle_at: datetime | None = None
        self._loop_cycles_completed: int = 0
        self._broadcast: Callable[[dict[str, Any]], None] | None = None

    def set_broadcast(self, fn: Callable[[dict[str, Any]], None]) -> None:
        """Set the WebSocket broadcast callback."""
        self._broadcast = fn

    def _emit(self, event: dict[str, Any]) -> None:
        if self._broadcast:
            self._broadcast(event)

    def has_active_job(self) -> bool:
        """Return True if a mutating job is currently running."""
        with self._lock:
            return self._active_job_id is not None

    def get_active_job(self) -> Job | None:
        """Return the currently running job, if any."""
        with self._lock:
            if self._active_job_id:
                return self._get_job(self._active_job_id)
            return None

    def start_job(
        self,
        job_type: str,
        run_fn: Callable[[Job, Callable[[dict[str, Any]], None]], None],
    ) -> Job:
        """Queue a generic background job. Raises ValueError if one is already active."""
        with self._lock:
            if self._active_job_id is not None:
                raise ValueError("A job is already running")
            job = Job(
                job_id=uuid.uuid4().hex[:12],
                job_type=job_type,
                status=JobStatus.QUEUED,
            )
            self._jobs.append(job)
            self._active_job_id = job.job_id

        thread = threading.Thread(
            target=self._run_job,
            args=(job, run_fn),
            daemon=True,
        )
        thread.start()
        return job

    def start_cycle(
        self,
        run_fn: Callable[[Job, Callable[[dict[str, Any]], None]], None],
    ) -> Job:
        """Queue a pipeline cycle. Raises ValueError if one is already active."""
        return self.start_job("pipeline_cycle", run_fn)

    def _run_job(
        self,
        job: Job,
        run_fn: Callable[[Job, Callable[[dict[str, Any]], None]], None],
    ) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        try:
            run_fn(job, self._emit)
            job.status = JobStatus.COMPLETED
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
        finally:
            job.completed_at = datetime.now(UTC)
            with self._lock:
                self._active_job_id = None

    # --- Loop management ---

    @property
    def loop_active(self) -> bool:
        """Return True if the polling loop is running."""
        return self._loop_thread is not None and self._loop_thread.is_alive()

    @property
    def loop_state(self) -> dict[str, Any]:
        """Return serialisable loop state."""
        return {
            "active": self.loop_active,
            "interval_min": self._loop_interval_min if self.loop_active else None,
            "started_at": (
                self._loop_started_at.isoformat()
                if self._loop_started_at and self.loop_active
                else None
            ),
            "last_cycle_at": (
                self._loop_last_cycle_at.isoformat() if self._loop_last_cycle_at else None
            ),
            "cycles_completed": self._loop_cycles_completed,
        }

    def start_loop(
        self,
        interval_min: int,
        run_fn: Callable[[Job, Callable[[dict[str, Any]], None]], None],
    ) -> dict[str, Any]:
        """Start the polling loop. Raises ValueError if already active."""
        if self.loop_active:
            raise ValueError("Loop is already active")
        self._loop_stop.clear()
        self._loop_interval_min = interval_min
        self._loop_started_at = datetime.now(UTC)
        self._loop_cycles_completed = 0
        self._loop_thread = threading.Thread(
            target=self._loop_worker,
            args=(interval_min, run_fn),
            daemon=True,
        )
        self._loop_thread.start()
        self._emit(
            {
                "type": "loop_status",
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {"active": True, "interval_min": interval_min},
            }
        )
        return {"loop_id": uuid.uuid4().hex[:12], "interval_min": interval_min}

    def stop_loop(self) -> None:
        """Stop the polling loop. Idempotent."""
        self._loop_stop.set()
        self._emit(
            {
                "type": "loop_status",
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {"active": False},
            }
        )

    def _loop_worker(
        self,
        interval_min: int,
        run_fn: Callable[[Job, Callable[[dict[str, Any]], None]], None],
    ) -> None:
        while not self._loop_stop.is_set():
            try:
                job = self.start_cycle(run_fn)
                # Wait for the job to finish
                while job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    time.sleep(0.5)
                self._loop_last_cycle_at = datetime.now(UTC)
                self._loop_cycles_completed += 1
            except ValueError:
                pass  # already running, skip this iteration
            # Sleep in 1-second increments so stop_loop is responsive
            for _ in range(interval_min * 60):
                if self._loop_stop.is_set():
                    return
                time.sleep(1)

    # --- Query ---

    def get_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Job]:
        """Return recent jobs, optionally filtered by status."""
        with self._lock:
            jobs = list(self._jobs)
        if status:
            jobs = [j for j in jobs if j.status.value == status]
        return list(reversed(jobs))[:limit]

    def get_job(self, job_id: str) -> Job | None:
        """Return a specific job by ID."""
        with self._lock:
            return self._get_job(job_id)

    def _get_job(self, job_id: str) -> Job | None:
        for j in self._jobs:
            if j.job_id == job_id:
                return j
        return None

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
