"""Risk endpoint tests.

Kelly-preview equivalence tests prove that the endpoint result matches direct
invocation of kelly_stake() from footy_ev.risk.kelly byte-for-byte across a
battery of inputs including edge cases.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from footy_ev.risk.kelly import kelly_stake

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_MOCK_EXPOSURE = {
    "today_open": "25.00",
    "total_open": "125.00",
    "per_fixture": [
        {
            "fixture_id": "EPL|2025-2026|arsenal|chelsea|2026-05-20",
            "open_stake": "25.00",
        }
    ],
}

_MOCK_BANKROLL = {
    "current": "985.00",
    "peak": "1000.00",
    "drawdown_pct": 0.015,
    "sparkline": [
        {"decided_at": "2026-05-20T09:00:00", "bankroll": "1000.00"},
        {"decided_at": "2026-05-21T10:00:00", "bankroll": "985.00"},
    ],
}


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


def _preview(c: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    r = c.post("/api/v1/risk/kelly-preview", json=payload)
    assert r.status_code == 200, r.text
    result: dict[str, Any] = r.json()
    return result


# ── Kelly preview equivalence: each test verifies stake == kelly_stake() ──────


def test_kelly_preview_normal_case() -> None:
    """Positive-edge case: stake matches kelly_stake(), intermediates are correct."""
    c = _client()
    _auth(c)
    payload = {
        "p_hat": 0.55,
        "sigma_p": 0.02,
        "odds": 2.1,
        "base_fraction": 0.25,
        "uncertainty_k": 1.0,
        "per_bet_cap_pct": 0.02,
        "recent_clv_pct": 0.0,
        "bankroll": "1000",
    }
    result = _preview(c, payload)
    expected = kelly_stake(
        0.55,
        0.02,
        2.1,
        1000.0,
        base_fraction=0.25,
        uncertainty_k=1.0,
        per_bet_cap_pct=0.02,
        recent_clv_pct=0.0,
    )
    assert Decimal(result["stake"]) == expected
    assert result["p_lb"] == pytest.approx(0.53, abs=1e-9)
    assert result["per_bet_cap_hit"] is False


def test_kelly_preview_zero_edge() -> None:
    """p_hat * odds = 1 (breakeven) → stake = 0."""
    c = _client()
    _auth(c)
    payload = {
        "p_hat": 0.40,
        "sigma_p": 0.00,
        "odds": 2.0,
        "base_fraction": 0.25,
        "uncertainty_k": 1.0,
        "per_bet_cap_pct": 0.02,
        "recent_clv_pct": 0.0,
        "bankroll": "1000",
    }
    result = _preview(c, payload)
    expected = kelly_stake(
        0.40,
        0.00,
        2.0,
        1000.0,
        base_fraction=0.25,
        uncertainty_k=1.0,
        per_bet_cap_pct=0.02,
        recent_clv_pct=0.0,
    )
    assert Decimal(result["stake"]) == expected
    assert Decimal(result["stake"]) == Decimal("0.00")


def test_kelly_preview_negative_edge() -> None:
    """Clear negative edge (p_hat < 1/odds) → stake = 0."""
    c = _client()
    _auth(c)
    payload = {
        "p_hat": 0.30,
        "sigma_p": 0.00,
        "odds": 2.5,
        "base_fraction": 0.25,
        "uncertainty_k": 1.0,
        "per_bet_cap_pct": 0.02,
        "recent_clv_pct": 0.0,
        "bankroll": "1000",
    }
    result = _preview(c, payload)
    expected = kelly_stake(
        0.30,
        0.00,
        2.5,
        1000.0,
        base_fraction=0.25,
        uncertainty_k=1.0,
        per_bet_cap_pct=0.02,
        recent_clv_pct=0.0,
    )
    assert Decimal(result["stake"]) == expected
    assert Decimal(result["stake"]) == Decimal("0.00")


def test_kelly_preview_cap_hit() -> None:
    """Large edge hits per_bet_cap → per_bet_cap_hit = True, stake = cap * bankroll."""
    c = _client()
    _auth(c)
    payload = {
        "p_hat": 0.90,
        "sigma_p": 0.00,
        "odds": 2.0,
        "base_fraction": 0.25,
        "uncertainty_k": 1.0,
        "per_bet_cap_pct": 0.02,
        "recent_clv_pct": 0.0,
        "bankroll": "1000",
    }
    result = _preview(c, payload)
    expected = kelly_stake(
        0.90,
        0.00,
        2.0,
        1000.0,
        base_fraction=0.25,
        uncertainty_k=1.0,
        per_bet_cap_pct=0.02,
        recent_clv_pct=0.0,
    )
    assert Decimal(result["stake"]) == expected
    assert result["per_bet_cap_hit"] is True
    # capped at 0.02 * 1000 = £20.00
    assert Decimal(result["stake"]) == Decimal("20.00")


def test_kelly_preview_clv_multiplier_shrink() -> None:
    """Negative CLV drives multiplier to floor 0.4."""
    c = _client()
    _auth(c)
    payload = {
        "p_hat": 0.55,
        "sigma_p": 0.00,
        "odds": 2.1,
        "base_fraction": 0.25,
        "uncertainty_k": 1.0,
        "per_bet_cap_pct": 0.02,
        "recent_clv_pct": -0.10,
        "bankroll": "1000",
    }
    result = _preview(c, payload)
    expected = kelly_stake(
        0.55,
        0.00,
        2.1,
        1000.0,
        base_fraction=0.25,
        uncertainty_k=1.0,
        per_bet_cap_pct=0.02,
        recent_clv_pct=-0.10,
    )
    assert Decimal(result["stake"]) == expected
    assert result["clv_multiplier"] == pytest.approx(0.4, abs=1e-9)


def test_kelly_preview_clv_multiplier_full() -> None:
    """CLV at +0.05 lifts multiplier to ceiling 1.0."""
    c = _client()
    _auth(c)
    payload = {
        "p_hat": 0.55,
        "sigma_p": 0.00,
        "odds": 2.1,
        "base_fraction": 0.25,
        "uncertainty_k": 1.0,
        "per_bet_cap_pct": 0.02,
        "recent_clv_pct": 0.05,
        "bankroll": "5000",
    }
    result = _preview(c, payload)
    expected = kelly_stake(
        0.55,
        0.00,
        2.1,
        5000.0,
        base_fraction=0.25,
        uncertainty_k=1.0,
        per_bet_cap_pct=0.02,
        recent_clv_pct=0.05,
    )
    assert Decimal(result["stake"]) == expected
    assert result["clv_multiplier"] == pytest.approx(1.0, abs=1e-9)


def test_kelly_preview_large_sigma_zero_stake() -> None:
    """sigma_p > p_hat drives p_lb to 0, stake = 0."""
    c = _client()
    _auth(c)
    payload = {
        "p_hat": 0.55,
        "sigma_p": 0.60,
        "odds": 2.1,
        "base_fraction": 0.25,
        "uncertainty_k": 1.0,
        "per_bet_cap_pct": 0.02,
        "recent_clv_pct": 0.0,
        "bankroll": "1000",
    }
    result = _preview(c, payload)
    expected = kelly_stake(
        0.55,
        0.60,
        2.1,
        1000.0,
        base_fraction=0.25,
        uncertainty_k=1.0,
        per_bet_cap_pct=0.02,
        recent_clv_pct=0.0,
    )
    assert Decimal(result["stake"]) == expected
    assert Decimal(result["stake"]) == Decimal("0.00")
    assert result["p_lb"] == 0.0


# ── Exposure / bankroll (mocked) ───────────────────────────────────────────────


@patch("footy_ev_api.routers.risk.get_exposure")
def test_exposure(mock_exp: Any) -> None:
    mock_exp.return_value = dict(_MOCK_EXPOSURE)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/risk/exposure")
    assert r.status_code == 200
    body = r.json()
    assert body["today_open"] == "25.00"
    assert body["total_open"] == "125.00"
    assert len(body["per_fixture"]) == 1
    assert body["per_fixture"][0]["open_stake"] == "25.00"


@patch("footy_ev_api.routers.risk.get_bankroll")
def test_bankroll(mock_bk: Any) -> None:
    mock_bk.return_value = dict(_MOCK_BANKROLL)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/risk/bankroll")
    assert r.status_code == 200
    body = r.json()
    assert body["current"] == "985.00"
    assert body["peak"] == "1000.00"
    assert body["drawdown_pct"] == pytest.approx(0.015, abs=1e-9)
    assert len(body["sparkline"]) == 2


def test_risk_requires_auth() -> None:
    c = _client()
    r = c.get("/api/v1/risk/exposure")
    assert r.status_code == 401
