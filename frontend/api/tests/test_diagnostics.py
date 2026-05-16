"""Diagnostics endpoint tests.

Key invariants:
  - Env endpoint never returns values, only set/unset booleans.
  - Circuit breaker reset is audit-logged (middleware fires).
  - Logs endpoint returns entries from in-memory buffer.
  - Auth required on all endpoints.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.adapters.circuit_breaker import reset_cb, trip_cb
from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    reset_cb()  # ensure clean state for each test
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


# ── Circuit breaker ────────────────────────────────────────────────────────────


def test_cb_get_ok_state() -> None:
    c = _client()
    _auth(c)
    r = c.get("/api/v1/diagnostics/circuit-breaker")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "ok"
    assert body["last_tripped_at"] is None
    assert body["reason"] is None


def test_cb_get_tripped_state() -> None:
    c = _client()
    trip_cb("unit test trip")  # trip AFTER _client() so reset_cb() doesn't clear it
    _auth(c)
    r = c.get("/api/v1/diagnostics/circuit-breaker")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "tripped"
    assert body["reason"] == "unit test trip"
    assert body["last_tripped_at"] is not None


def test_cb_reset() -> None:
    trip_cb("reset test")
    c = _client()
    _auth(c)
    r = c.post("/api/v1/diagnostics/circuit-breaker/reset")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "ok"


@patch("footy_ev_api.middleware.audit._write_audit_row")
def test_cb_reset_is_audit_logged(mock_write: Any) -> None:
    """POST /diagnostics/circuit-breaker/reset must trigger an audit row."""
    c = _client()
    _auth(c)
    r = c.post("/api/v1/diagnostics/circuit-breaker/reset")
    assert r.status_code == 200
    # The middleware should have called _write_audit_row with action_type='circuit_breaker_reset'
    assert mock_write.called
    call_args = mock_write.call_args
    assert call_args[0][0] == "circuit_breaker_reset"


# ── Logs ────────────────────────────────────────────────────────────────────────


def test_logs_returns_list() -> None:
    import logging

    logger = logging.getLogger("test.diagnostics")
    logger.warning("test log entry for stage 11")

    c = _client()
    _auth(c)
    r = c.get("/api/v1/diagnostics/logs")
    assert r.status_code == 200
    body = r.json()
    assert "entries" in body
    assert "total" in body
    assert isinstance(body["entries"], list)


def test_logs_level_filter() -> None:
    c = _client()
    _auth(c)
    r = c.get("/api/v1/diagnostics/logs?level=ERROR&limit=10")
    assert r.status_code == 200
    body = r.json()
    for entry in body["entries"]:
        assert entry["level"] == "ERROR"


def test_logs_limit_respected() -> None:
    c = _client()
    _auth(c)
    r = c.get("/api/v1/diagnostics/logs?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["entries"]) <= 5


# ── Migrations ─────────────────────────────────────────────────────────────────


def test_migrations_list() -> None:
    c = _client()
    _auth(c)
    r = c.get("/api/v1/diagnostics/migrations")
    assert r.status_code == 200
    body = r.json()
    assert "migrations" in body
    migrations = body["migrations"]
    assert isinstance(migrations, list)
    assert len(migrations) >= 15  # we have 015 migrations now
    # All should have applied=True
    for m in migrations:
        assert m["applied"] is True
        assert m["name"].endswith(".sql")


# ── Env ────────────────────────────────────────────────────────────────────────


def test_env_check_never_returns_values() -> None:
    """Env endpoint must only return name+is_set+required — never values."""
    c = _client()
    _auth(c)
    r = c.get("/api/v1/diagnostics/env")
    assert r.status_code == 200
    body = r.json()
    assert "vars" in body
    for var in body["vars"]:
        assert "name" in var
        assert "is_set" in var
        assert "required" in var
        # Must NOT contain any 'value' field
        assert "value" not in var
        assert isinstance(var["is_set"], bool)


def test_env_check_ui_operator_token_detected() -> None:
    """UI_OPERATOR_TOKEN is set (we set it in _client()), so is_set must be True."""
    c = _client()
    _auth(c)
    r = c.get("/api/v1/diagnostics/env")
    assert r.status_code == 200
    body = r.json()
    token_var = next((v for v in body["vars"] if v["name"] == "UI_OPERATOR_TOKEN"), None)
    assert token_var is not None
    assert token_var["is_set"] is True
    assert token_var["required"] is True


# ── Auth guard ─────────────────────────────────────────────────────────────────


def test_diagnostics_requires_auth() -> None:
    c = _client()
    for url, method in [
        ("/api/v1/diagnostics/circuit-breaker", "GET"),
        ("/api/v1/diagnostics/circuit-breaker/reset", "POST"),
        ("/api/v1/diagnostics/logs", "GET"),
        ("/api/v1/diagnostics/migrations", "GET"),
        ("/api/v1/diagnostics/env", "GET"),
    ]:
        r = c.request(method, url)
        assert r.status_code == 401, f"{method} {url} should require auth"
