"""In-memory circuit breaker state singleton.

State is reset when the server restarts. This is intentional — the CB is a
runtime safeguard, not a persistent ledger. A future stage can persist it to
operator_actions (TRIP events) if needed.
"""

from __future__ import annotations

from datetime import UTC, datetime

_STATE: dict[str, str | None] = {
    "state": "ok",
    "last_tripped_at": None,
    "reason": None,
}


def get_cb_state() -> dict[str, str | None]:
    """Return current circuit breaker state (copy)."""
    return dict(_STATE)


def reset_cb() -> dict[str, str | None]:
    """Reset circuit breaker to 'ok'. Returns new state."""
    _STATE["state"] = "ok"
    _STATE["last_tripped_at"] = None
    _STATE["reason"] = None
    return dict(_STATE)


def trip_cb(reason: str) -> dict[str, str | None]:
    """Trip the circuit breaker with a reason. Returns new state."""
    _STATE["state"] = "tripped"
    _STATE["last_tripped_at"] = datetime.now(UTC).isoformat()
    _STATE["reason"] = reason
    return dict(_STATE)
