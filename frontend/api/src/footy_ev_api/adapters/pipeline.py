"""Thin adapter around the existing footy_ev pipeline.

Wraps ``footy_ev.runtime.run_once`` for use by the API's JobManager.
If the main project dependencies are missing (e.g. running frontend
in isolation), the adapter gracefully degrades with a stub.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from footy_ev_api.jobs.manager import Job

_LOG = logging.getLogger(__name__)

PIPELINE_NODES = ["scraper", "news", "analyst", "pricing", "risk", "execution"]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def run_pipeline_cycle(
    job: Job,
    broadcast: Callable[[dict[str, Any]], None],
) -> None:
    """Run one full pipeline cycle in the calling thread.

    Attempts to import and invoke ``footy_ev.runtime.run_once``.
    If the main project isn't importable, falls back to a stub that
    simulates node progression so the UI can be developed independently.
    """
    broadcast(
        {
            "type": "cycle_started",
            "timestamp": _now_iso(),
            "payload": {"job_id": job.job_id},
        }
    )
    job.progress.append({"type": "cycle_started", "timestamp": _now_iso()})

    started = time.monotonic()

    try:
        from pathlib import Path

        from footy_ev.runtime import PaperTraderConfig, run_once

        cfg = PaperTraderConfig(db_path=Path("data/warehouse/footy_ev.duckdb"))

        for node in PIPELINE_NODES:
            broadcast(
                {
                    "type": "node_started",
                    "timestamp": _now_iso(),
                    "payload": {"node": node, "job_id": job.job_id},
                }
            )
            job.progress.append({"type": "node_started", "node": node, "timestamp": _now_iso()})

        result = run_once(cfg)

        for node in PIPELINE_NODES:
            broadcast(
                {
                    "type": "node_complete",
                    "timestamp": _now_iso(),
                    "payload": {"node": node, "job_id": job.job_id},
                }
            )
            job.progress.append({"type": "node_complete", "node": node, "timestamp": _now_iso()})

        duration = round(time.monotonic() - started, 2)
        broadcast(
            {
                "type": "cycle_finished",
                "timestamp": _now_iso(),
                "payload": {
                    "job_id": job.job_id,
                    "duration_s": duration,
                    "result": {
                        k: v
                        for k, v in result.items()
                        if k in ("n_fixtures", "n_candidates", "n_approved", "breaker_tripped")
                    },
                },
            }
        )
        job.progress.append(
            {"type": "cycle_finished", "duration_s": duration, "timestamp": _now_iso()}
        )

    except ImportError:
        _LOG.warning("footy_ev not importable — running stub pipeline cycle")
        _run_stub_cycle(job, broadcast, started)

    except Exception as exc:
        duration = round(time.monotonic() - started, 2)
        broadcast(
            {
                "type": "cycle_failed",
                "timestamp": _now_iso(),
                "payload": {"job_id": job.job_id, "error": str(exc), "duration_s": duration},
            }
        )
        job.progress.append({"type": "cycle_failed", "error": str(exc), "timestamp": _now_iso()})
        raise


def _run_stub_cycle(
    job: Job,
    broadcast: Callable[[dict[str, Any]], None],
    started: float,
) -> None:
    """Simulated pipeline cycle for UI development without the main project."""
    for node in PIPELINE_NODES:
        broadcast(
            {
                "type": "node_started",
                "timestamp": _now_iso(),
                "payload": {"node": node, "job_id": job.job_id},
            }
        )
        job.progress.append({"type": "node_started", "node": node, "timestamp": _now_iso()})
        time.sleep(0.3)
        broadcast(
            {
                "type": "node_complete",
                "timestamp": _now_iso(),
                "payload": {"node": node, "job_id": job.job_id},
            }
        )
        job.progress.append({"type": "node_complete", "node": node, "timestamp": _now_iso()})

    duration = round(time.monotonic() - started, 2)
    broadcast(
        {
            "type": "cycle_finished",
            "timestamp": _now_iso(),
            "payload": {
                "job_id": job.job_id,
                "duration_s": duration,
                "result": {
                    "n_fixtures": 0,
                    "n_candidates": 0,
                    "n_approved": 0,
                    "breaker_tripped": False,
                },
            },
        }
    )
    job.progress.append({"type": "cycle_finished", "duration_s": duration, "timestamp": _now_iso()})
