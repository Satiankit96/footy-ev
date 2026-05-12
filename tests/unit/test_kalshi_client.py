"""Unit tests for KalshiClient and price helpers.

All tests are offline — no network access. RSA key fixtures generate fresh
in-memory 2048-bit keys. HTTP is mocked via httpx.MockTransport.

Covers:
  - price_to_decimal_odds / decimal_odds_to_price round-trips
  - _KalshiCredentialError raised when env vars missing or PEM unreadable
  - list_events parses KalshiEvent list from mock HTTP response
  - list_markets parses KalshiMarket list and filters by floor_strike
  - get_market parses single KalshiMarket from mock HTTP response
  - _KalshiServerError raised on 5xx; _KalshiAPIError raised on 4xx
  - KalshiResponse is frozen
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from footy_ev.venues.kalshi import (
    DEMO_BASE_URL,
    KalshiClient,
    KalshiEvent,
    KalshiMarket,
    KalshiResponse,
    _KalshiAPIError,
    _KalshiCredentialError,
    _KalshiServerError,
    decimal_odds_to_price,
    price_to_decimal_odds,
)

# ---------------------------------------------------------------------------
# Test RSA key helpers
# ---------------------------------------------------------------------------


def _make_rsa_pem(key_size: int = 2048) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _make_client(
    transport: httpx.BaseTransport,
    *,
    base_url: str = DEMO_BASE_URL,
) -> KalshiClient:
    return KalshiClient(
        api_key_id="test-key-id",
        private_key_pem=_make_rsa_pem(),
        base_url=base_url,
        transport=transport,
    )


def _static_transport(status: int, body: Any) -> httpx.MockTransport:
    """Returns a transport that always responds with (status, json body)."""
    raw = json.dumps(body).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=raw, headers={"Content-Type": "application/json"})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def test_price_to_decimal_odds_basic() -> None:
    odds = price_to_decimal_odds(0.5)
    assert abs(odds - 2.0) < 1e-9


def test_price_to_decimal_odds_55_cents() -> None:
    odds = price_to_decimal_odds(0.55)
    assert abs(odds - (1.0 / 0.55)) < 1e-9


def test_price_to_decimal_odds_rejects_zero() -> None:
    with pytest.raises(ValueError, match="must be in"):
        price_to_decimal_odds(0.0)


def test_price_to_decimal_odds_rejects_one() -> None:
    with pytest.raises(ValueError, match="must be in"):
        price_to_decimal_odds(1.0)


def test_price_to_decimal_odds_rejects_above_one() -> None:
    with pytest.raises(ValueError, match="must be in"):
        price_to_decimal_odds(1.5)


def test_decimal_odds_to_price_roundtrip() -> None:
    for p in [0.30, 0.45, 0.55, 0.70, 0.80]:
        odds = price_to_decimal_odds(p)
        back = decimal_odds_to_price(odds)
        assert abs(back - p) < 0.01, f"roundtrip failed for p={p}"


def test_decimal_odds_to_price_clamps_to_range() -> None:
    assert decimal_odds_to_price(1.001) == 0.99
    assert decimal_odds_to_price(100.0) == 0.01


def test_decimal_odds_to_price_rejects_lte_one() -> None:
    with pytest.raises(ValueError, match="must be > 1.0"):
        decimal_odds_to_price(1.0)


# ---------------------------------------------------------------------------
# Credential errors
# ---------------------------------------------------------------------------


def test_from_env_raises_credential_error_no_key_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    pem = tmp_path / "key.pem"
    pem.write_bytes(b"fake_pem")
    with pytest.raises(_KalshiCredentialError, match="KALSHI_API_KEY_ID"):
        KalshiClient.from_env(pem_path=pem)


def test_from_env_raises_credential_error_missing_pem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    missing_pem = tmp_path / "nonexistent.pem"
    with pytest.raises(_KalshiCredentialError, match="Cannot read"):
        KalshiClient.from_env(pem_path=missing_pem)


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------

_EVENTS_BODY = {
    "events": [
        {
            "event_ticker": "KXEPLTOTAL-26MAY24WHULEE",
            "series_ticker": "KXEPLTOTAL",
            "title": "West Ham vs Leeds United: Total Goals",
            "sub_title": "WHU vs LEE (May 24)",
            "category": "Sports",
            "last_updated_ts": "2026-05-08T02:37:22.546783Z",
            "available_on_brokers": False,
            "mutually_exclusive": False,
        }
    ],
    "milestones": [],
}


def test_list_events_returns_kalshi_event_list() -> None:
    client = _make_client(_static_transport(200, _EVENTS_BODY))
    resp = client.list_events()
    assert isinstance(resp, KalshiResponse)
    assert isinstance(resp.payload, list)
    assert len(resp.payload) == 1
    event = resp.payload[0]
    assert isinstance(event, KalshiEvent)
    assert event.event_ticker == "KXEPLTOTAL-26MAY24WHULEE"
    assert event.series_ticker == "KXEPLTOTAL"
    assert event.title == "West Ham vs Leeds United: Total Goals"


def test_list_events_ignores_unknown_fields() -> None:
    body = {
        "events": [
            {
                "event_ticker": "KXEPLTOTAL-26MAY24WHULEE",
                "series_ticker": "KXEPLTOTAL",
                "title": "WHU vs LEE",
                "unknown_field_from_future_api": "should be ignored",
            }
        ]
    }
    client = _make_client(_static_transport(200, body))
    resp = client.list_events()
    assert resp.payload[0].event_ticker == "KXEPLTOTAL-26MAY24WHULEE"


def test_list_events_raises_server_error_on_5xx() -> None:
    client = _make_client(_static_transport(503, {"error": "service unavailable"}))
    with pytest.raises(_KalshiServerError):
        client.list_events()


def test_list_events_raises_api_error_on_4xx() -> None:
    client = _make_client(_static_transport(401, {"error": "unauthorized"}))
    with pytest.raises(_KalshiAPIError):
        client.list_events()


# ---------------------------------------------------------------------------
# list_markets
# ---------------------------------------------------------------------------

_MARKET_OBJ = {
    "ticker": "KXEPLTOTAL-26MAY24WHULEE-2",
    "event_ticker": "KXEPLTOTAL-26MAY24WHULEE",
    "floor_strike": 2.5,
    "status": "active",
    "title": "Will over 2.5 goals be scored?",
    "close_time": "2026-06-07T15:00:00Z",
    "yes_bid_dollars": "0.5500",
    "no_bid_dollars": "0.4300",
    "yes_ask_dollars": "0.5700",
    "no_ask_dollars": "0.4500",
    "yes_bid_size_fp": "50.00",
    "yes_ask_size_fp": "40.00",
    "can_close_early": True,
}

_MARKETS_BODY = {
    "markets": [
        _MARKET_OBJ,
        {
            **_MARKET_OBJ,
            "ticker": "KXEPLTOTAL-26MAY24WHULEE-4",
            "floor_strike": 4.5,
            "title": "Will over 4.5 goals be scored?",
        },
    ],
    "cursor": "",
}


def test_list_markets_returns_kalshi_market_list() -> None:
    client = _make_client(_static_transport(200, _MARKETS_BODY))
    resp = client.list_markets(event_ticker="KXEPLTOTAL-26MAY24WHULEE")
    assert isinstance(resp.payload, list)
    assert len(resp.payload) == 2
    mkt = resp.payload[0]
    assert isinstance(mkt, KalshiMarket)
    assert mkt.ticker == "KXEPLTOTAL-26MAY24WHULEE-2"
    assert mkt.floor_strike == Decimal("2.5")
    assert mkt.yes_bid_dollars == Decimal("0.5500")


def test_list_markets_floor_strike_filter() -> None:
    client = _make_client(_static_transport(200, _MARKETS_BODY))
    resp = client.list_markets(
        event_ticker="KXEPLTOTAL-26MAY24WHULEE",
        floor_strike_filter=Decimal("2.5"),
    )
    assert len(resp.payload) == 1
    assert resp.payload[0].floor_strike == Decimal("2.5")


def test_list_markets_floor_strike_filter_no_match() -> None:
    client = _make_client(_static_transport(200, _MARKETS_BODY))
    resp = client.list_markets(
        event_ticker="KXEPLTOTAL-26MAY24WHULEE",
        floor_strike_filter=Decimal("99.5"),
    )
    assert resp.payload == []


def test_list_markets_decimal_coercion_from_string_prices() -> None:
    client = _make_client(_static_transport(200, _MARKETS_BODY))
    resp = client.list_markets(event_ticker="KXEPLTOTAL-26MAY24WHULEE")
    mkt = resp.payload[0]
    assert isinstance(mkt.yes_bid_dollars, Decimal)
    assert isinstance(mkt.floor_strike, Decimal)
    assert isinstance(mkt.yes_bid_size_fp, float)


# ---------------------------------------------------------------------------
# get_market
# ---------------------------------------------------------------------------

_SINGLE_MARKET_BODY = {"market": _MARKET_OBJ}


def test_get_market_returns_single_kalshi_market() -> None:
    client = _make_client(_static_transport(200, _SINGLE_MARKET_BODY))
    resp = client.get_market("KXEPLTOTAL-26MAY24WHULEE-2")
    assert isinstance(resp.payload, KalshiMarket)
    assert resp.payload.ticker == "KXEPLTOTAL-26MAY24WHULEE-2"
    assert resp.payload.floor_strike == Decimal("2.5")


# ---------------------------------------------------------------------------
# KalshiResponse
# ---------------------------------------------------------------------------


def test_kalshi_response_is_frozen() -> None:
    from datetime import UTC, datetime

    r = KalshiResponse(payload={"foo": "bar"}, received_at=datetime.now(tz=UTC))
    with pytest.raises((AttributeError, TypeError)):
        r.payload = "mutated"  # type: ignore[misc]
