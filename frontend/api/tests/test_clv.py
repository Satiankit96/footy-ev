"""CLV endpoint tests with mocked adapter."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_MOCK_ROLLING = [
    {
        "bet_index": 1,
        "decided_at": "2026-05-20T09:00:00",
        "clv_pct": 0.03,
        "rolling_clv": 0.03,
        "cumulative_clv": 0.03,
    },
    {
        "bet_index": 2,
        "decided_at": "2026-05-21T10:00:00",
        "clv_pct": -0.01,
        "rolling_clv": 0.01,
        "cumulative_clv": 0.01,
    },
]

_MOCK_BREAKDOWN = [
    {
        "fixture_id": "EPL|2025-2026|arsenal|chelsea|2026-05-20",
        "market": "ou_2.5",
        "selection": "over",
        "mean_clv": 0.025,
        "n_bets": 2,
        "total_staked": "25.00",
        "total_pnl": "5.50",
    },
]

_MOCK_SOURCES = [
    {"source": "kalshi", "n_bets": 10, "mean_clv": 0.02},
    {"source": "missing", "n_bets": 3, "mean_clv": None},
]


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


@patch("footy_ev_api.routers.clv.get_clv_rolling")
def test_clv_rolling(mock_rolling: Any) -> None:
    mock_rolling.return_value = _MOCK_ROLLING
    c = _client()
    _auth(c)
    r = c.get("/api/v1/clv/rolling?window=100")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["clv_pct"] == 0.03
    assert body[1]["rolling_clv"] == 0.01


@patch("footy_ev_api.routers.clv.get_clv_breakdown")
def test_clv_breakdown(mock_bd: Any) -> None:
    mock_bd.return_value = _MOCK_BREAKDOWN
    c = _client()
    _auth(c)
    r = c.get("/api/v1/clv/breakdown")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["mean_clv"] == 0.025


@patch("footy_ev_api.routers.clv.get_clv_sources")
def test_clv_sources(mock_src: Any) -> None:
    mock_src.return_value = _MOCK_SOURCES
    c = _client()
    _auth(c)
    r = c.get("/api/v1/clv/sources")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["source"] == "kalshi"
    assert body[1]["mean_clv"] is None


@patch("footy_ev_api.routers.clv.run_clv_backfill")
def test_clv_backfill(mock_bf: Any) -> None:
    c = _client()
    _auth(c)
    r = c.post("/api/v1/clv/backfill", json={"from_date": "2026-01-01", "to_date": "2026-05-01"})
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["status"] in ("queued", "running", "completed")


def test_clv_requires_auth() -> None:
    c = _client()
    r = c.get("/api/v1/clv/rolling")
    assert r.status_code == 401
