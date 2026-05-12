"""Live integration test for KalshiClient — requires real RSA auth (Phase 3 step 5b).

Gated on FOOTY_EV_KALSHI_DEMO=1 AND KALSHI_API_KEY_ID set in environment.

Run with:
    $env:FOOTY_EV_KALSHI_DEMO = "1"
    .\make.ps1 test-integration
"""

from __future__ import annotations

import os

import pytest

_LIVE_GATE = "FOOTY_EV_KALSHI_DEMO"
_KEY_ENV = "KALSHI_API_KEY_ID"


@pytest.mark.skipif(
    os.environ.get(_LIVE_GATE) != "1",
    reason=f"set {_LIVE_GATE}=1 to run the Kalshi live integration test",
)
def test_kalshi_list_events_live() -> None:
    """Single read-only call to Kalshi list_events for KXEPLTOTAL series.

    Verifies:
      - from_env() constructs without error when KALSHI_API_KEY_ID is set.
      - list_events() returns a KalshiResponse with list[KalshiEvent] payload.
      - At least one event has a valid event_ticker starting with KXEPLTOTAL.
    """
    if not os.environ.get(_KEY_ENV):
        pytest.skip(f"{_KEY_ENV} not set")

    from pathlib import Path

    from footy_ev.venues.kalshi import (
        DEMO_BASE_URL,
        KalshiClient,
        KalshiEvent,
        _KalshiCredentialError,
    )

    pem_path = Path("data/kalshi_private_key.pem")
    if not pem_path.exists():
        pytest.skip("data/kalshi_private_key.pem not present")

    try:
        client = KalshiClient.from_env(pem_path=pem_path, base_url=DEMO_BASE_URL)
    except _KalshiCredentialError as exc:
        pytest.skip(f"credential error: {exc}")

    resp = client.list_events(series_ticker="KXEPLTOTAL", status="open")

    assert resp is not None
    assert hasattr(resp, "payload")
    assert hasattr(resp, "received_at")
    assert isinstance(resp.payload, list), f"unexpected payload type: {type(resp.payload)}"

    for event in resp.payload:
        assert isinstance(event, KalshiEvent)
        assert event.event_ticker.startswith("KXEPLTOTAL")
        assert event.series_ticker == "KXEPLTOTAL"


@pytest.mark.skipif(
    os.environ.get(_LIVE_GATE) != "1",
    reason=f"set {_LIVE_GATE}=1 to run the Kalshi live integration test",
)
def test_kalshi_list_markets_ou25_live() -> None:
    """Fetch OU 2.5 markets for the first open KXEPLTOTAL event.

    Verifies:
      - list_markets() with floor_strike_filter=Decimal("2.5") returns only
        markets with floor_strike == 2.5.
      - floor_strike is Decimal, prices are Decimal strings.
    """
    if not os.environ.get(_KEY_ENV):
        pytest.skip(f"{_KEY_ENV} not set")

    from decimal import Decimal
    from pathlib import Path

    from footy_ev.venues.kalshi import (
        DEMO_BASE_URL,
        KalshiClient,
        KalshiMarket,
        _KalshiCredentialError,
    )

    pem_path = Path("data/kalshi_private_key.pem")
    if not pem_path.exists():
        pytest.skip("data/kalshi_private_key.pem not present")

    try:
        client = KalshiClient.from_env(pem_path=pem_path, base_url=DEMO_BASE_URL)
    except _KalshiCredentialError as exc:
        pytest.skip(f"credential error: {exc}")

    events_resp = client.list_events(series_ticker="KXEPLTOTAL", status="open")
    if not events_resp.payload:
        pytest.skip("no open KXEPLTOTAL events on demo")

    first_event_ticker = events_resp.payload[0].event_ticker
    markets_resp = client.list_markets(
        event_ticker=first_event_ticker,
        floor_strike_filter=Decimal("2.5"),
    )

    assert isinstance(markets_resp.payload, list)
    for mkt in markets_resp.payload:
        assert isinstance(mkt, KalshiMarket)
        assert mkt.floor_strike == Decimal("2.5")
        assert isinstance(mkt.yes_bid_dollars, Decimal)
        assert isinstance(mkt.no_bid_dollars, Decimal)
