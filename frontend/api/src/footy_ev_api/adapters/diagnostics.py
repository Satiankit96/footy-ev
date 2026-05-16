"""Diagnostics adapter — circuit breaker, logs, migrations, env."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from footy_ev.db import MIGRATIONS_DIR

from footy_ev_api.adapters.circuit_breaker import (
    get_cb_state,
    reset_cb,
)
from footy_ev_api.middleware.audit import get_log_tail

# Ordered list of expected env vars: (name, required).
_EXPECTED_VARS: list[tuple[str, bool]] = [
    ("UI_OPERATOR_TOKEN", True),
    ("KALSHI_API_KEY_ID", False),
    ("KALSHI_PRIVATE_KEY_PATH", False),
    ("KALSHI_BASE_URL", False),
    ("DUCKDB_PATH", False),
    ("LIVE_TRADING", False),
    ("LOG_LEVEL", False),
    ("LLM_EXTRACTOR", False),
    ("GEMINI_API_KEY", False),
    ("FOOTBALL_DATA_ORG_KEY", False),
    ("THE_ODDS_API_KEY", False),
    ("GITHUB_TOKEN", False),
]


def get_circuit_breaker() -> dict[str, str | None]:
    """Return current circuit breaker state."""
    return get_cb_state()


def do_circuit_breaker_reset() -> dict[str, str | None]:
    """Reset circuit breaker and return new state."""
    return reset_cb()


def list_migrations() -> dict[str, Any]:
    """List all migration files with applied status and file timestamps."""
    migrations: list[dict[str, Any]] = []
    if MIGRATIONS_DIR.exists():
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, UTC).isoformat()
            migrations.append(
                {
                    "name": f.name,
                    "applied": True,
                    "applied_at": mtime,
                }
            )
    return {"migrations": migrations}


def check_env() -> dict[str, Any]:
    """Return set/unset status for expected env vars. Never returns values."""
    return {
        "vars": [
            {
                "name": name,
                "is_set": bool(os.environ.get(name)),
                "required": required,
            }
            for name, required in _EXPECTED_VARS
        ]
    }


def get_logs(
    level: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return recent log entries from the in-memory buffer."""
    entries = get_log_tail(level=level, since=since, limit=limit)
    return {"entries": entries, "total": len(entries)}
