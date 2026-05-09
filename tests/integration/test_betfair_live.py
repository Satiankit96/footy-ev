"""Live Betfair Delayed-API integration test, gated on FOOTY_EV_BETFAIR_LIVE=1.

Skips cleanly when:
  - the env var is unset (default for everyone without an account)
  - any of BETFAIR_APP_KEY / BETFAIR_USERNAME / BETFAIR_PASSWORD is empty

When opted-in, runs a single read-only `list_events` call against the
real Delayed API to confirm credentials work and the API contract is
unchanged. No bets, no writes.
"""

from __future__ import annotations

import os

import pytest

from footy_ev.venues import BetfairClient

_LIVE_FLAG = "FOOTY_EV_BETFAIR_LIVE"
_REQUIRED = ("BETFAIR_APP_KEY", "BETFAIR_USERNAME", "BETFAIR_PASSWORD")


def _live_enabled() -> bool:
    if os.environ.get(_LIVE_FLAG) != "1":
        return False
    return all(os.environ.get(k) for k in _REQUIRED)


@pytest.mark.skipif(
    not _live_enabled(),
    reason=(
        f"set {_LIVE_FLAG}=1 and all of {', '.join(_REQUIRED)} in .env to run "
        "the live Betfair Delayed-API integration test (free tier, read-only)."
    ),
)
def test_live_list_events_returns_payload() -> None:
    client = BetfairClient(
        app_key=os.environ["BETFAIR_APP_KEY"],
        username=os.environ["BETFAIR_USERNAME"],
        password=os.environ["BETFAIR_PASSWORD"],
    )
    resp = client.list_events(country_codes=["GB"], days_ahead=7)
    # The list may be empty out of season but the call must succeed.
    assert isinstance(resp.payload, list)
    assert resp.received_at is not None
    assert resp.staleness_seconds >= 0
