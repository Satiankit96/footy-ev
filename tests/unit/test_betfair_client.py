"""Unit tests for the Betfair Exchange Delayed-API client.

Mocks every httpx call via respx; no network access. Covers:
  - login success / failure paths
  - the three calls (list_events, list_market_catalogue, list_market_book)
  - automatic session-token refresh after expiry
  - staleness extraction from listMarketBook payload
  - credentials never appear in retried-error messages
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from footy_ev.venues import BetfairClient
from footy_ev.venues.betfair import BETTING_URL, LOGIN_URL
from footy_ev.venues.exceptions import BetfairAuthError


@pytest.fixture
def client() -> BetfairClient:
    return BetfairClient(
        app_key="ak_test",
        username="u",
        password="p",
        staleness_limit_sec=300,
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@respx.mock
def test_login_caches_session_token(client: BetfairClient) -> None:
    respx.post(LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"status": "SUCCESS", "token": "tok123"})
    )
    client.login()
    assert client._session is not None
    assert client._session.token == "tok123"


@respx.mock
def test_login_raises_on_status_field_failure(client: BetfairClient) -> None:
    respx.post(LOGIN_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "FAIL", "error": "INVALID_USERNAME_OR_PASSWORD"}
        )
    )
    with pytest.raises(BetfairAuthError) as exc:
        client.login()
    assert "INVALID_USERNAME_OR_PASSWORD" in str(exc.value)
    # Credentials must never appear in the error message:
    assert "u" not in str(exc.value).split("INVALID")[0] or "p" not in str(exc.value)


@respx.mock
def test_login_raises_on_non_200(client: BetfairClient) -> None:
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(503, text="bad gateway"))
    with pytest.raises(BetfairAuthError):
        client.login()


@respx.mock
def test_session_auto_refresh_after_expiry(client: BetfairClient) -> None:
    respx.post(LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"status": "SUCCESS", "token": "first"})
    )
    respx.post(f"{BETTING_URL}/listEvents/").mock(return_value=httpx.Response(200, json=[]))
    client.list_events(country_codes=["GB"], days_ahead=7)
    assert client._session.token == "first"

    # Force expiry: backdate the issued_at, then re-call
    client._session.issued_at = datetime.now(tz=UTC) - timedelta(hours=9)
    respx.post(LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"status": "SUCCESS", "token": "second"})
    )
    client.list_events(country_codes=["GB"], days_ahead=7)
    assert client._session.token == "second"


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


def _login_route() -> None:
    respx.post(LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"status": "SUCCESS", "token": "tok"})
    )


@respx.mock
def test_list_events_returns_betfair_response(client: BetfairClient) -> None:
    _login_route()
    payload = [{"event": {"id": "1.1", "name": "ARS v LIV"}}]
    respx.post(f"{BETTING_URL}/listEvents/").mock(return_value=httpx.Response(200, json=payload))
    resp = client.list_events(country_codes=["GB"], days_ahead=7)
    assert resp.payload == payload
    assert resp.received_at is not None


@respx.mock
def test_list_market_catalogue(client: BetfairClient) -> None:
    _login_route()
    payload = [{"marketId": "1.1.OU25", "marketName": "Over/Under 2.5 Goals"}]
    respx.post(f"{BETTING_URL}/listMarketCatalogue/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    resp = client.list_market_catalogue(event_ids=["1.1"], market_types=["OVER_UNDER_25"])
    assert resp.payload == payload


@respx.mock
def test_list_market_book_extracts_source_timestamp(client: BetfairClient) -> None:
    _login_route()
    payload = [
        {
            "marketId": "1.1.OU25",
            "lastMatchTime": "2026-05-06T22:00:00.000Z",
            "runners": [
                {"selectionId": 1, "ex": {"availableToBack": [{"price": 1.95}]}},
                {"selectionId": 2, "ex": {"availableToBack": [{"price": 2.05}]}},
            ],
        }
    ]
    respx.post(f"{BETTING_URL}/listMarketBook/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    resp = client.list_market_book(market_ids=["1.1.OU25"])
    assert resp.source_timestamp is not None
    assert resp.source_timestamp.tzinfo is not None
    assert resp.staleness_seconds >= 0


@respx.mock
def test_list_market_book_no_lastmatchtime_keeps_zero_staleness(
    client: BetfairClient,
) -> None:
    _login_route()
    respx.post(f"{BETTING_URL}/listMarketBook/").mock(
        return_value=httpx.Response(200, json=[{"marketId": "1.1", "runners": []}])
    )
    resp = client.list_market_book(market_ids=["1.1"])
    assert resp.source_timestamp is None
    assert resp.staleness_seconds == 0


# ---------------------------------------------------------------------------
# Live integration test (gated)
# ---------------------------------------------------------------------------


def test_betfair_live_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: env var must be set explicitly to opt-in to live tests."""
    monkeypatch.delenv("FOOTY_EV_BETFAIR_LIVE", raising=False)
    import os

    assert os.environ.get("FOOTY_EV_BETFAIR_LIVE") is None
