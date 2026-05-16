"""Live-trading gate endpoint tests.

Key invariants:
  - GET /live-trading/status always returns enabled=False regardless of env.
  - POST /live-trading/check-conditions is read-only.
  - POST/PUT /live-trading/enable returns 405.
  - Auth required on all endpoints.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


# ── Status endpoint ────────────────────────────────────────────────────────────


def test_status_always_disabled() -> None:
    """enabled must always be False regardless of env."""
    c = _client()
    _auth(c)
    r = c.get("/api/v1/live-trading/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False


def test_status_disabled_even_when_env_set() -> None:
    """Even if LIVE_TRADING=true in env, API still returns enabled=False."""
    os.environ["LIVE_TRADING"] = "true"
    c = _client()
    _auth(c)
    r = c.get("/api/v1/live-trading/status")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    del os.environ["LIVE_TRADING"]


def test_status_has_gate_reasons() -> None:
    c = _client()
    _auth(c)
    r = c.get("/api/v1/live-trading/status")
    body = r.json()
    assert "gate_reasons" in body
    assert isinstance(body["gate_reasons"], list)
    assert len(body["gate_reasons"]) > 0


# ── check-conditions ───────────────────────────────────────────────────────────


@patch("footy_ev_api.adapters.live_trading._connect_ro", return_value=None)
def test_check_conditions_no_warehouse(mock_connect: Any) -> None:
    """When warehouse is absent, conditions return met=False with zero counts."""
    c = _client()
    _auth(c)
    r = c.post("/api/v1/live-trading/check-conditions")
    assert r.status_code == 200
    body = r.json()
    assert body["clv_condition"]["met"] is False
    assert body["clv_condition"]["bet_count"] == 0
    assert body["all_met"] is False


@patch("footy_ev_api.adapters.live_trading._connect_ro", return_value=None)
def test_check_conditions_bankroll_not_set(mock_connect: Any) -> None:
    """When BANKROLL_DISCIPLINE_CONFIRMED is unset, bankroll condition is unmet."""
    os.environ.pop("BANKROLL_DISCIPLINE_CONFIRMED", None)
    c = _client()
    _auth(c)
    r = c.post("/api/v1/live-trading/check-conditions")
    assert r.status_code == 200
    body = r.json()
    assert body["bankroll_condition"]["met"] is False
    assert body["bankroll_condition"]["flag_set"] is False
    assert body["bankroll_condition"]["flag_name"] == "BANKROLL_DISCIPLINE_CONFIRMED"


@patch("footy_ev_api.adapters.live_trading._connect_ro", return_value=None)
def test_check_conditions_bankroll_set(mock_connect: Any) -> None:
    """When BANKROLL_DISCIPLINE_CONFIRMED is set, bankroll condition is met."""
    os.environ["BANKROLL_DISCIPLINE_CONFIRMED"] = "true"
    c = _client()
    _auth(c)
    r = c.post("/api/v1/live-trading/check-conditions")
    assert r.status_code == 200
    body = r.json()
    assert body["bankroll_condition"]["met"] is True
    assert body["bankroll_condition"]["flag_set"] is True
    del os.environ["BANKROLL_DISCIPLINE_CONFIRMED"]


@patch("footy_ev_api.adapters.live_trading._connect_ro", return_value=None)
def test_check_conditions_response_shape(mock_connect: Any) -> None:
    """Response must have clv_condition, bankroll_condition, all_met."""
    c = _client()
    _auth(c)
    r = c.post("/api/v1/live-trading/check-conditions")
    assert r.status_code == 200
    body = r.json()
    assert "clv_condition" in body
    assert "bankroll_condition" in body
    assert "all_met" in body
    clv = body["clv_condition"]
    assert "met" in clv
    assert "bet_count" in clv
    assert "days_span" in clv
    assert "mean_clv_pct" in clv


# ── Enable endpoint blocked ────────────────────────────────────────────────────


def test_enable_post_returns_405() -> None:
    """POST /live-trading/enable must return 405."""
    c = _client()
    _auth(c)
    r = c.post("/api/v1/live-trading/enable")
    assert r.status_code == 405


def test_enable_put_returns_405() -> None:
    """PUT /live-trading/enable must return 405."""
    c = _client()
    _auth(c)
    r = c.put("/api/v1/live-trading/enable")
    assert r.status_code == 405


# ── Auth guard ─────────────────────────────────────────────────────────────────


def test_live_trading_requires_auth() -> None:
    c = _client()
    for url, method in [
        ("/api/v1/live-trading/status", "GET"),
        ("/api/v1/live-trading/check-conditions", "POST"),
    ]:
        r = c.request(method, url)
        assert r.status_code == 401, f"{method} {url} should require auth"
