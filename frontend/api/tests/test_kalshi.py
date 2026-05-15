"""Kalshi endpoint tests with mocked KalshiClient."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
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


@dataclass(frozen=True)
class _FakeResponse:
    payload: Any
    received_at: datetime = datetime(2026, 5, 14, tzinfo=UTC)


@dataclass
class _FakeEvent:
    event_ticker: str = "KXEPLTOTAL-26MAY14TEST"
    series_ticker: str = "KXEPLTOTAL"
    title: str = "Test Event"
    sub_title: str = ""
    category: str = "football"


@dataclass
class _FakeMarket:
    ticker: str = "KXEPLTOTAL-26MAY14TEST-2"
    event_ticker: str = "KXEPLTOTAL-26MAY14TEST"
    floor_strike: Decimal = Decimal("2.5")
    yes_bid_dollars: Decimal = Decimal("0.5500")
    no_bid_dollars: Decimal = Decimal("0.4500")
    yes_ask_dollars: Decimal = Decimal("0.5700")
    no_ask_dollars: Decimal = Decimal("0.4300")
    yes_bid_size_fp: float = 10.0
    yes_ask_size_fp: float = 5.0
    status: str = "open"
    title: str = "Over/Under 2.5"
    close_time: str = ""


class _MockKalshiClient:
    base_url: str = "https://demo-api.kalshi.co/trade-api/v2"

    def list_events(self, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(payload=[_FakeEvent()])

    def list_markets(self, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(payload=[_FakeMarket()])

    def get_market(self, ticker: str) -> _FakeResponse:
        return _FakeResponse(payload=_FakeMarket(ticker=ticker))


def test_kalshi_credentials_status():
    c = _client()
    _auth(c)
    r = c.get("/api/v1/kalshi/credentials/status")
    assert r.status_code == 200
    body = r.json()
    assert "configured" in body
    assert "key_id_present" in body
    assert "private_key_present" in body
    assert "base_url" in body
    assert "is_demo" in body
    assert "KALSHI_API_KEY_ID" not in str(body)


def test_kalshi_not_configured():
    c = _client()
    _auth(c)
    os.environ.pop("KALSHI_API_KEY_ID", None)
    os.environ.pop("KALSHI_API_BASE_URL", None)
    r = c.get("/api/v1/kalshi/health")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "KALSHI_NOT_CONFIGURED"


@patch("footy_ev_api.routers.kalshi.get_kalshi_client", return_value=_MockKalshiClient())
@patch("footy_ev_api.routers.kalshi.check_health")
def test_kalshi_health_with_mock(mock_check: Any, mock_client: Any):
    mock_check.return_value = {
        "ok": True,
        "latency_ms": 42.5,
        "clock_skew_s": 0.3,
        "base_url": "https://demo-api.kalshi.co/trade-api/v2",
        "error": None,
    }
    c = _client()
    _auth(c)
    r = c.get("/api/v1/kalshi/health")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
    assert "latency_ms" in body
    assert body["latency_ms"] is not None
    assert "base_url" in body


@patch("footy_ev_api.routers.kalshi.get_kalshi_client", return_value=_MockKalshiClient())
def test_kalshi_events_list(mock_client: Any):
    c = _client()
    _auth(c)
    r = c.get("/api/v1/kalshi/events")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert "total" in body
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert event["event_ticker"] == "KXEPLTOTAL-26MAY14TEST"
    assert event["series_ticker"] == "KXEPLTOTAL"


@patch("footy_ev_api.routers.kalshi.get_kalshi_client", return_value=_MockKalshiClient())
def test_kalshi_event_detail(mock_client: Any):
    c = _client()
    _auth(c)
    r = c.get("/api/v1/kalshi/events/KXEPLTOTAL-26MAY14TEST")
    assert r.status_code == 200
    body = r.json()
    assert "event" in body
    assert "markets" in body
    assert body["event"]["event_ticker"] == "KXEPLTOTAL-26MAY14TEST"
    assert len(body["markets"]) == 1


@patch("footy_ev_api.routers.kalshi.get_kalshi_client", return_value=_MockKalshiClient())
def test_kalshi_market_detail(mock_client: Any):
    c = _client()
    _auth(c)
    r = c.get("/api/v1/kalshi/markets/KXEPLTOTAL-26MAY14TEST-2")
    assert r.status_code == 200
    body = r.json()
    assert "market" in body
    m = body["market"]
    assert m["ticker"] == "KXEPLTOTAL-26MAY14TEST-2"
    assert m["yes_bid"] == "0.5500"
    assert m["no_bid"] == "0.4500"
    assert m["decimal_odds"] is not None
    odds = float(m["decimal_odds"])
    assert abs(odds - (1.0 / 0.55)) < 0.01
    assert m["implied_probability"] is not None
    prob = float(m["implied_probability"])
    assert abs(prob - 55.0) < 0.1


@patch("footy_ev_api.routers.kalshi.get_kalshi_client", return_value=_MockKalshiClient())
@patch("footy_ev_api.routers.kalshi._query_aliases")
def test_kalshi_events_include_alias_status(mock_aliases: Any, mock_client: Any):
    mock_aliases.return_value = {
        "KXEPLTOTAL-26MAY14TEST": {"alias_status": "resolved", "fixture_id": "FIX-001"},
    }
    c = _client()
    _auth(c)
    r = c.get("/api/v1/kalshi/events")
    assert r.status_code == 200
    event = r.json()["events"][0]
    assert event["alias_status"] == "resolved"
    assert event["fixture_id"] == "FIX-001"
