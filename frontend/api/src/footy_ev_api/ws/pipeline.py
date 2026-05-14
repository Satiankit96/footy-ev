"""WebSocket endpoints for pipeline events and freshness ticks."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from footy_ev_api.auth import decode_session_jwt
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)

_pipeline_clients: set[WebSocket] = set()
_freshness_clients: set[WebSocket] = set()


def _validate_ws_token(token: str | None) -> bool:
    """Validate a JWT token passed as query parameter."""
    if not token:
        return False
    try:
        settings = Settings()
        decode_session_jwt(token, settings)
        return True
    except Exception:
        return False


async def broadcast_pipeline_event(event: dict[str, Any]) -> None:
    """Send a pipeline event to all connected WebSocket clients."""
    dead: set[WebSocket] = set()
    message = json.dumps(event)
    for ws in _pipeline_clients.copy():
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    _pipeline_clients.difference_update(dead)


def sync_broadcast(event: dict[str, Any]) -> None:
    """Synchronous wrapper for broadcast — called from background threads."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_pipeline_event(event))
    except RuntimeError:
        import asyncio as _asyncio

        try:
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(broadcast_pipeline_event(event))
            else:
                loop.run_until_complete(broadcast_pipeline_event(event))
        except Exception:
            _LOG.debug("No event loop for WS broadcast — skipping")


async def ws_pipeline(websocket: WebSocket) -> None:
    """WebSocket /ws/v1/pipeline — broadcasts pipeline cycle events."""
    token = websocket.query_params.get("token")
    if not _validate_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    _pipeline_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _pipeline_clients.discard(websocket)


async def ws_freshness(websocket: WebSocket) -> None:
    """WebSocket /ws/v1/freshness — pushes freshness state every 5 seconds."""
    token = websocket.query_params.get("token")
    if not _validate_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    _freshness_clients.add(websocket)
    try:
        while True:
            from datetime import UTC, datetime

            from footy_ev_api.routers.pipeline import _freshness_stub

            fresh = _freshness_stub()
            payload = {
                "type": "freshness_tick",
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {k: v.model_dump() for k, v in fresh.items()},
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    except Exception:
        _LOG.debug("Freshness WS error", exc_info=True)
    finally:
        _freshness_clients.discard(websocket)
