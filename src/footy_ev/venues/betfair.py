"""Betfair Exchange Delayed-API client (Phase 3 step 1).

Free-tier "Delayed Application Key" only. The Delayed key is rate-limited
and returns market data with an approximate one-minute lag — adequate for
paper trading and CLV measurement against Betfair SP, not for in-running
arbitrage.

Three calls are wired:
  - list_events               (find upcoming fixtures by country+days_ahead)
  - list_market_catalogue     (resolve markets for selected events)
  - list_market_book          (current odds + liquidity for selected markets)

All three return a BetfairResponse(received_at, source_timestamp, payload)
so the orchestration layer can compute staleness and trip the circuit
breaker without re-querying the venue (BLUE_MAP §1.3).

Authentication uses the simple username/password flow against
identitysso.betfair.com (returns sessionToken). Cert-login is supported
by Betfair but requires uploading an x509 cert; the free tier does not
need it. Credentials come from .env only and are never logged. Tenacity
wraps every external call with exponential-backoff retries on transient
HTTP errors.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from footy_ev.venues.exceptions import BetfairAuthError

_LOG = logging.getLogger(__name__)

LOGIN_URL = "https://identitysso.betfair.com/api/login"
BETTING_URL = "https://api.betfair.com/exchange/betting/rest/v1.0"
SESSION_TTL = timedelta(hours=8)
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)


@dataclass(frozen=True)
class BetfairResponse:
    """Wraps a payload with our wall-clock receipt timestamp.

    Staleness is computed against `received_at`, which is set inside
    the client at the moment the HTTP response was parsed.
    """

    payload: Any
    received_at: datetime
    source_timestamp: datetime | None = None
    staleness_seconds: int = 0


@dataclass
class _Session:
    token: str
    issued_at: datetime

    def is_expired(self, now: datetime, ttl: timedelta = SESSION_TTL) -> bool:
        return now - self.issued_at >= ttl


@dataclass
class BetfairClient:
    app_key: str
    username: str
    password: str
    staleness_limit_sec: int = 300
    transport: httpx.BaseTransport | None = None
    _session: _Session | None = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, BetfairAuthError)),
        reraise=True,
    )
    def login(self) -> None:
        """Exchange username+password for a Betfair sessionToken."""
        with self._http() as client:
            r = client.post(
                LOGIN_URL,
                data={"username": self.username, "password": self.password},
                headers={
                    "X-Application": self.app_key,
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if r.status_code != httpx.codes.OK:
                raise BetfairAuthError(f"login http {r.status_code}; status_field=<redacted>")
            body = r.json()
            if body.get("status") != "SUCCESS":
                raise BetfairAuthError(
                    f"login failed: status={body.get('status')!r} error={body.get('error')!r}"
                )
            self._session = _Session(
                token=body["token"],
                issued_at=datetime.now(tz=UTC),
            )
            _LOG.info("betfair: login succeeded; session token cached for 8h")

    def _ensure_session(self) -> _Session:
        now = datetime.now(tz=UTC)
        if self._session is None or self._session.is_expired(now):
            self.login()
        assert self._session is not None
        return self._session

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------
    def list_events(
        self,
        *,
        country_codes: list[str],
        days_ahead: int,
        event_type_ids: list[str] | None = None,
    ) -> BetfairResponse:
        """Returns upcoming events (fixtures) for the given countries.

        event_type_ids defaults to ["1"] (Soccer).
        """
        now = datetime.now(tz=UTC)
        market_filter = {
            "eventTypeIds": event_type_ids or ["1"],
            "marketCountries": country_codes,
            "marketStartTime": {
                "from": now.isoformat(),
                "to": (now + timedelta(days=days_ahead)).isoformat(),
            },
        }
        out: BetfairResponse = self._post("listEvents/", {"filter": market_filter})
        return out

    def list_market_catalogue(
        self,
        *,
        event_ids: list[str],
        market_types: list[str],
        max_results: int = 200,
    ) -> BetfairResponse:
        """Resolve markets (e.g. MATCH_ODDS, OVER_UNDER_25) for given events."""
        body = {
            "filter": {
                "eventIds": event_ids,
                "marketTypeCodes": market_types,
            },
            "marketProjection": [
                "RUNNER_DESCRIPTION",
                "MARKET_START_TIME",
                "EVENT",
            ],
            "maxResults": max_results,
        }
        out: BetfairResponse = self._post("listMarketCatalogue/", body)
        return out

    def list_market_book(
        self,
        *,
        market_ids: list[str],
        price_data: tuple[str, ...] = ("EX_BEST_OFFERS",),
    ) -> BetfairResponse:
        """Current odds + liquidity for the given markets."""
        body = {
            "marketIds": market_ids,
            "priceProjection": {"priceData": list(price_data)},
        }
        out: BetfairResponse = self._post("listMarketBook/", body)
        return out

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------
    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _post(self, path: str, body: dict[str, Any]) -> BetfairResponse:
        session = self._ensure_session()
        with self._http() as client:
            r = client.post(
                f"{BETTING_URL}/{path}",
                content=json.dumps(body),
                headers={
                    "X-Application": self.app_key,
                    "X-Authentication": session.token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            r.raise_for_status()
            received_at = datetime.now(tz=UTC)
            payload = r.json()
            source_timestamp = _extract_source_timestamp(payload)
            staleness = _staleness_seconds(source_timestamp, received_at)
            return BetfairResponse(
                payload=payload,
                received_at=received_at,
                source_timestamp=source_timestamp,
                staleness_seconds=staleness,
            )

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=DEFAULT_TIMEOUT, transport=self.transport)


def _extract_source_timestamp(payload: Any) -> datetime | None:
    """Pull a representative venue timestamp out of the payload, if present.

    listMarketBook responses include a per-market `lastMatchTime`; we use
    the most recent one. listEvents and listMarketCatalogue do not carry
    a useful source timestamp, in which case we return None and the
    orchestrator falls back to received_at.
    """
    if not isinstance(payload, list):
        return None
    candidates: list[datetime] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("lastMatchTime")
        if isinstance(ts, str):
            try:
                candidates.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except ValueError:
                continue
    if not candidates:
        return None
    return max(candidates)


def _staleness_seconds(source_ts: datetime | None, received_at: datetime) -> int:
    if source_ts is None:
        return 0
    delta = (received_at - source_ts).total_seconds()
    return max(0, int(delta))
