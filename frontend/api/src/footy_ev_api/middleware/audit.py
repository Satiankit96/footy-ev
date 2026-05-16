"""Audit middleware — intercepts every state-mutating request and writes an
operator_actions row after successful completion.

Design constraints:
  - Only logs 2xx responses on POST/PUT/DELETE to auditable paths.
  - Sanitises input_params: any field whose name matches token|key|secret|password
    is replaced with "[REDACTED]".
  - If the audit DB write fails (warehouse missing, locked, etc.), logs a warning
    and returns the response normally — never blocks the operator.
  - Also hosts the in-memory log buffer used by GET /diagnostics/logs.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_LOG = logging.getLogger(__name__)


# ── In-memory log capture ─────────────────────────────────────────────────────


class _MemoryLogHandler(logging.Handler):
    """Rolling in-memory buffer of recent log records."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self._records: deque[dict[str, str]] = deque(maxlen=capacity)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        ts = datetime.fromtimestamp(record.created, UTC).isoformat()
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001
            message = record.getMessage()
        self._records.append(
            {
                "timestamp": ts,
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
        )

    def tail(
        self,
        level: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, str]]:
        records = list(self._records)
        if level:
            lvl = level.upper()
            records = [r for r in records if r["level"] == lvl]
        if since:
            records = [r for r in records if r["timestamp"] >= since]
        return records[-limit:]


_LOG_HANDLER = _MemoryLogHandler()


def setup_log_capture() -> None:
    """Register the in-memory log handler on the root logger. Call once at startup."""
    root = logging.getLogger()
    if _LOG_HANDLER not in root.handlers:
        root.addHandler(_LOG_HANDLER)


def get_log_tail(
    level: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> list[dict[str, str]]:
    """Return recent log entries from the in-memory buffer."""
    return _LOG_HANDLER.tail(level=level, since=since, limit=limit)


# ── Audit path registry ───────────────────────────────────────────────────────

_SENSITIVE = re.compile(r"token|key|secret|password|credential", re.IGNORECASE)

_EXACT_ACTIONS: dict[str, str] = {
    "/api/v1/pipeline/cycle": "pipeline_cycle",
    "/api/v1/pipeline/loop/start": "pipeline_loop_start",
    "/api/v1/pipeline/loop/stop": "pipeline_loop_stop",
    "/api/v1/bootstrap/run": "bootstrap_run",
    "/api/v1/aliases": "alias_create",
    "/api/v1/predictions/run": "prediction_run",
    "/api/v1/clv/backfill": "clv_backfill",
    "/api/v1/diagnostics/circuit-breaker/reset": "circuit_breaker_reset",
}


def _get_action_type(method: str, path: str) -> str | None:
    """Return the audit action_type for this request, or None if not auditable."""
    if method not in {"POST", "PUT", "DELETE"}:
        return None
    if path in _EXACT_ACTIONS:
        return _EXACT_ACTIONS[path]
    if path.startswith("/api/v1/aliases/") and path.endswith("/retire"):
        return "alias_retire"
    return None


def _sanitize_params(body_bytes: bytes) -> dict[str, Any] | None:
    """Parse JSON body and redact sensitive fields. Returns None on parse failure."""
    if not body_bytes:
        return None
    try:
        raw = json.loads(body_bytes)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return {k: "[REDACTED]" if _SENSITIVE.search(k) else v for k, v in raw.items()}


# ── Audit DB write ────────────────────────────────────────────────────────────


def _write_audit_row(
    action_type: str,
    input_params: dict[str, Any] | None,
    result_summary: str,
    request_id: str,
) -> None:
    """Insert one audit row into operator_actions. Silently no-ops if warehouse absent."""
    from footy_ev_api.settings import Settings

    db = Path(Settings().warehouse_path)
    if not db.exists():
        _LOG.warning("Audit write skipped — warehouse not found: %s", db)
        return
    try:
        con = duckdb.connect(str(db), read_only=False)
        try:
            con.execute(
                "INSERT INTO operator_actions "
                "(action_id, action_type, operator, performed_at, "
                " input_params, result_summary, request_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    str(uuid.uuid4()),
                    action_type,
                    "operator",
                    datetime.now(UTC),
                    json.dumps(input_params) if input_params is not None else None,
                    result_summary,
                    request_id or None,
                ],
            )
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Audit write failed for %s: %s", action_type, exc)


# ── Middleware ─────────────────────────────────────────────────────────────────


class AuditMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware that appends an operator_actions row after
    every successful state-mutating request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        body_bytes = b""
        if request.method in {"POST", "PUT", "DELETE"}:
            body_bytes = await request.body()

        response = await call_next(request)

        action_type = _get_action_type(request.method, request.url.path)
        if action_type and 200 <= response.status_code < 300:
            request_id = request.headers.get("x-request-id", "")
            input_params = _sanitize_params(body_bytes)
            result_summary = f"{action_type} succeeded (HTTP {response.status_code})"
            try:
                _write_audit_row(action_type, input_params, result_summary, request_id)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("Audit write failed for %s: %s", action_type, exc)

        return response
