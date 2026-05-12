"""Live integration test for KalshiClient — requires real RSA auth (Phase 3 step 5b).

Gated on FOOTY_EV_KALSHI_LIVE=1 AND KALSHI_API_KEY_ID set in environment.
Until Phase 3 step 5b is complete, KalshiClient.get_events() raises
NotImplementedError — this test will skip or xfail in that case.

Run with:
    $env:FOOTY_EV_KALSHI_LIVE = "1"
    .\make.ps1 test-integration
"""

from __future__ import annotations

import os

import pytest

_LIVE_GATE = "FOOTY_EV_KALSHI_LIVE"
_KEY_ENV = "KALSHI_API_KEY_ID"


@pytest.mark.skipif(
    os.environ.get(_LIVE_GATE) != "1",
    reason=f"set {_LIVE_GATE}=1 to run the Kalshi live integration test",
)
def test_kalshi_get_events_live() -> None:
    """Single read-only call to Kalshi get_events for KXEPLTOTAL series.

    Verifies:
      - from_env() constructs without error when KALSHI_API_KEY_ID is set.
      - get_events() either returns a KalshiResponse (step 5b) or raises
        NotImplementedError (step 5a). The test xfails on NotImplementedError
        so CI knows the path exists but auth is not wired yet.
    """
    if not os.environ.get(_KEY_ENV):
        pytest.skip(f"{_KEY_ENV} not set")

    from pathlib import Path

    from footy_ev.venues.kalshi import DEMO_BASE_URL, KalshiClient, _KalshiCredentialError

    pem_path = Path("data/kalshi_private_key.pem")
    if not pem_path.exists():
        pytest.skip("data/kalshi_private_key.pem not present")

    try:
        client = KalshiClient.from_env(pem_path=pem_path, base_url=DEMO_BASE_URL)
    except _KalshiCredentialError as exc:
        pytest.skip(f"credential error: {exc}")

    try:
        resp = client.get_events(series_ticker="KXEPLTOTAL", status="open")
    except NotImplementedError:
        pytest.xfail("KalshiClient.get_events() not yet implemented (Phase 3 step 5a stub)")

    assert resp is not None
    assert hasattr(resp, "payload")
    assert hasattr(resp, "received_at")
    payload = resp.payload
    assert isinstance(payload, (list, dict)), f"unexpected payload type: {type(payload)}"
