"""Paper bets endpoint tests with mocked adapter."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_MOCK_BET = {
    "decision_id": "bet001",
    "fixture_id": "EPL|2025-2026|arsenal|chelsea|2026-05-20",
    "market": "ou_2.5",
    "selection": "over",
    "odds_at_decision": 2.1,
    "stake_gbp": "12.50",
    "edge_pct": 0.055,
    "kelly_fraction_used": 0.0125,
    "settlement_status": "pending",
    "clv_pct": None,
    "decided_at": "2026-05-20T09:00:00",
    "venue": "kalshi",
}

_MOCK_KELLY = {
    "p_hat": 0.55,
    "sigma_p": 0.03,
    "uncertainty_k": 1.0,
    "p_lb": 0.52,
    "b": 1.1,
    "q": 0.48,
    "f_full": 0.0727,
    "base_fraction": 0.25,
    "per_bet_cap_pct": 0.02,
    "f_used": 0.0125,
    "per_bet_cap_hit": False,
    "bankroll_used": "1000.00",
}

_MOCK_EDGE_MATH = {
    "p_calibrated": 0.55,
    "odds_decimal": 2.1,
    "commission": 0.0,
    "edge": 0.055,
    "edge_pct_stored": 0.055,
}

_MOCK_BET_DETAIL = {
    **_MOCK_BET,
    "run_id": "run_abc",
    "sigma_p": 0.03,
    "bankroll_used": "1000.00",
    "features_hash": "deadbeef",
    "settled_at": None,
    "pnl_gbp": None,
    "closing_odds": None,
    "kelly_breakdown": _MOCK_KELLY,
    "edge_math": _MOCK_EDGE_MATH,
}

_MOCK_SUMMARY = {
    "period": "all",
    "total_bets": 5,
    "wins": 2,
    "losses": 2,
    "pending": 1,
    "total_pnl": "8.25",
    "total_staked": "62.50",
    "roi": 0.132,
    "mean_clv": 0.022,
    "min_clv": -0.03,
    "max_clv": 0.08,
}


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


@patch("footy_ev_api.routers.bets.list_bets")
def test_list_bets(mock_list: Any) -> None:
    mock_list.return_value = {"bets": [_MOCK_BET], "total": 1}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bets")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["bets"][0]["market"] == "ou_2.5"
    assert body["bets"][0]["stake_gbp"] == "12.50"


@patch("footy_ev_api.routers.bets.list_bets")
def test_list_bets_filters(mock_list: Any) -> None:
    mock_list.return_value = {"bets": [], "total": 0}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bets?status=pending&venue=kalshi&limit=25&offset=0")
    assert r.status_code == 200
    mock_list.assert_called_once_with(
        status="pending",
        fixture_id=None,
        venue="kalshi",
        date_from=None,
        date_to=None,
        limit=25,
        offset=0,
    )


@patch("footy_ev_api.routers.bets.get_bet")
def test_bet_detail(mock_get: Any) -> None:
    mock_get.return_value = dict(_MOCK_BET_DETAIL)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bets/bet001")
    assert r.status_code == 200
    body = r.json()
    assert body["decision_id"] == "bet001"
    assert body["kelly_breakdown"]["p_lb"] == 0.52
    assert body["edge_math"]["edge"] == 0.055


@patch("footy_ev_api.routers.bets.get_bet")
def test_bet_detail_not_found(mock_get: Any) -> None:
    mock_get.return_value = None
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bets/nonexistent")
    assert r.status_code == 404


@patch("footy_ev_api.routers.bets.get_bets_summary")
def test_bets_summary(mock_sum: Any) -> None:
    mock_sum.return_value = dict(_MOCK_SUMMARY)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bets/summary?period=30d")
    assert r.status_code == 200
    body = r.json()
    assert body["total_bets"] == 5
    assert body["roi"] == 0.132


@patch("footy_ev_api.routers.bets.get_clv_rolling")
def test_bets_clv_rolling(mock_rolling: Any) -> None:
    mock_rolling.return_value = [
        {
            "bet_index": 1,
            "decided_at": "2026-05-20T09:00:00",
            "clv_pct": 0.03,
            "rolling_clv": 0.03,
            "cumulative_clv": 0.03,
        },
    ]
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bets/clv/rolling?window=50")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["bet_index"] == 1


def test_bets_requires_auth() -> None:
    c = _client()
    r = c.get("/api/v1/bets")
    assert r.status_code == 401
