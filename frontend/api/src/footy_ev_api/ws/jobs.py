"""WebSocket endpoint for per-job progress events."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from footy_ev_api.auth import decode_session_jwt
from footy_ev_api.jobs.manager import JobManager, JobStatus
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)

_job_clients: dict[str, set[WebSocket]] = {}


def _validate_ws_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        settings = Settings()
        decode_session_jwt(token, settings)
        return True
    except Exception:
        return False


async def broadcast_job_event(job_id: str, event: dict[str, Any]) -> None:
    """Send an event to all WebSocket clients watching a specific job."""
    clients = _job_clients.get(job_id, set())
    if not clients:
        return
    dead: set[WebSocket] = set()
    message = json.dumps(event)
    for ws in clients.copy():
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


def sync_broadcast_job(event: dict[str, Any]) -> None:
    """Sync wrapper for job broadcasts — called from background threads."""
    job_id = event.get("payload", {}).get("job_id", "")
    if not job_id:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_job_event(job_id, event))
    except RuntimeError:
        _LOG.debug("No event loop for job WS broadcast — skipping")


async def ws_job(websocket: WebSocket, job_id: str) -> None:
    """WebSocket /ws/v1/jobs/{job_id} — streams progress for a specific job."""
    token = websocket.query_params.get("token")
    if not _validate_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    mgr = JobManager()
    job = mgr.get_job(job_id)
    if job is None:
        await websocket.close(code=4004, reason="Job not found")
        return

    await websocket.accept()

    if job_id not in _job_clients:
        _job_clients[job_id] = set()
    _job_clients[job_id].add(websocket)

    try:
        for event in job.progress:
            await websocket.send_text(json.dumps(event))

        while job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            await asyncio.sleep(0.5)
            for event in job.progress[len(job.progress) :]:
                await websocket.send_text(json.dumps(event))

        final_event = {
            "type": "completed" if job.status == JobStatus.COMPLETED else "failed",
            "payload": {
                "job_id": job_id,
                "status": job.status.value,
                "error": job.error,
            },
        }
        await websocket.send_text(json.dumps(final_event))

    except WebSocketDisconnect:
        pass
    except Exception:
        _LOG.debug("Job WS error", exc_info=True)
    finally:
        _job_clients.get(job_id, set()).discard(websocket)
        if job_id in _job_clients and not _job_clients[job_id]:
            del _job_clients[job_id]
