"""Kalshi Exchange client — Phase 3 step 5b implementation.

RSA-PSS/SHA256 per-request signing with Pydantic-validated response models.

Auth headers:
  KALSHI-ACCESS-KEY        — key ID from env var KALSHI_API_KEY_ID
  KALSHI-ACCESS-SIGNATURE  — base64(RSA-PSS-SHA256(timestamp + METHOD + path))
  KALSHI-ACCESS-TIMESTAMP  — millisecond epoch as string

Private PEM at data/kalshi_private_key.pem (gitignored).
Key ID from env var KALSHI_API_KEY_ID.

Price convention: Kalshi prices are 4-decimal strings, e.g. "0.5500".
YES contract = over the floor_strike threshold for total-goals markets.
Use price_to_decimal_odds() / decimal_odds_to_price() for conversion.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_LOG = logging.getLogger(__name__)

DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"
PROD_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
DEFAULT_PEM_PATH = Path("data/kalshi_private_key.pem")

# Kalshi EPL total goals series ticker
KXEPLTOTAL_SERIES = "KXEPLTOTAL"

# OU 2.5 floor_strike for filtering
OU25_FLOOR_STRIKE = Decimal("2.5")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class _KalshiCredentialError(Exception):
    """Raised at client init when required credentials are missing or unreadable."""


class _KalshiSigningError(Exception):
    """Raised when RSA signing fails (corrupted PEM, non-RSA key, runtime error)."""


class _KalshiServerError(Exception):
    """5xx response from Kalshi API — transient, retried by tenacity."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Kalshi API {status}: {body[:200]}")
        self.status = status


class _KalshiAPIError(Exception):
    """4xx response from Kalshi API — non-transient, not retried."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Kalshi API {status}: {body[:200]}")
        self.status = status


# ---------------------------------------------------------------------------
# Pydantic response models (shapes verified against demo capture 2026-05-12)
# ---------------------------------------------------------------------------


class KalshiEvent(BaseModel):
    """One event from GET /events?series_ticker=KXEPLTOTAL."""

    model_config = {"extra": "ignore"}

    event_ticker: str
    series_ticker: str
    title: str
    sub_title: str = ""
    category: str = ""
    last_updated_ts: str = ""


class KalshiMarket(BaseModel):
    """One market from GET /markets or GET /markets/<ticker>.

    Monetary fields are Decimal (parsed from 4-decimal strings like "0.5500").
    Size/liquidity fields are float (acceptable for intel only, not money math).
    floor_strike is Decimal (may arrive as float 2.5 or string "2.5" from API).
    """

    model_config = {"extra": "ignore"}

    ticker: str
    event_ticker: str
    floor_strike: Decimal
    status: str = ""
    title: str = ""
    close_time: str = ""

    # Price fields: API returns 4-decimal strings, e.g. "0.5500" or "0.0000"
    yes_bid_dollars: Decimal = Decimal("0")
    no_bid_dollars: Decimal = Decimal("0")
    yes_ask_dollars: Decimal = Decimal("0")
    no_ask_dollars: Decimal = Decimal("0")

    # Size fields: API returns strings like "0.00"; float is acceptable for liquidity
    yes_bid_size_fp: float = 0.0
    yes_ask_size_fp: float = 0.0

    @field_validator(
        "floor_strike",
        "yes_bid_dollars",
        "no_bid_dollars",
        "yes_ask_dollars",
        "no_ask_dollars",
        mode="before",
    )
    @classmethod
    def _coerce_decimal(cls, v: Any) -> Decimal:
        return Decimal(str(v))

    @field_validator("yes_bid_size_fp", "yes_ask_size_fp", mode="before")
    @classmethod
    def _coerce_float(cls, v: Any) -> float:
        return float(v)


# ---------------------------------------------------------------------------
# Response wrapper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KalshiResponse:
    """Wraps a Kalshi API payload with wall-clock receipt timestamp."""

    payload: Any
    received_at: datetime
    source_timestamp: datetime | None = None
    staleness_seconds: int = 0


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def price_to_decimal_odds(yes_bid_dollars: float) -> float:
    """Convert a Kalshi YES bid price to decimal odds.

    Args:
        yes_bid_dollars: Kalshi yes_bid_dollars field, a float in (0, 1).
            Represents the probability that the YES contract settles at $1.

    Returns:
        Decimal odds = 1 / yes_bid_dollars. E.g. 0.55 → 1.818.

    Raises:
        ValueError: if yes_bid_dollars is outside (0, 1).
    """
    if not (0.0 < yes_bid_dollars < 1.0):
        raise ValueError(f"yes_bid_dollars must be in (0, 1), got {yes_bid_dollars!r}")
    return 1.0 / yes_bid_dollars


def decimal_odds_to_price(odds: float) -> float:
    """Convert decimal odds back to a Kalshi YES price in dollars.

    Args:
        odds: decimal odds (must be > 1.0).

    Returns:
        YES price in dollars, clamped to [0.01, 0.99] and rounded to 2dp.
    """
    if odds <= 1.0:
        raise ValueError(f"decimal odds must be > 1.0, got {odds!r}")
    raw = 1.0 / odds
    return round(max(0.01, min(0.99, raw)), 2)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass
class KalshiClient:
    """Kalshi Exchange API client with RSA-PSS/SHA256 per-request signing.

    Args:
        api_key_id: Kalshi key ID (KALSHI_API_KEY_ID env var).
        private_key_pem: raw PEM bytes of the RSA private key.
        base_url: override to use demo environment for testing.
        staleness_limit_sec: max acceptable staleness for odds snapshots.
        transport: optional httpx transport override (for tests).
    """

    api_key_id: str
    private_key_pem: bytes
    base_url: str = PROD_BASE_URL
    staleness_limit_sec: int = 300
    transport: httpx.BaseTransport | None = None
    _private_key_pem: bytes = field(default=b"", init=False, repr=False)
    _signing_key: Any = field(default=None, init=False, repr=False)
    _api_path_prefix: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        self._private_key_pem = self.private_key_pem
        # Compute API path prefix from base_url, e.g. "/trade-api/v2"
        self._api_path_prefix = urlparse(self.base_url).path.rstrip("/")

    @classmethod
    def from_env(
        cls,
        *,
        pem_path: Path = DEFAULT_PEM_PATH,
        base_url: str = PROD_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> KalshiClient:
        """Construct from environment variables.

        Reads:
          KALSHI_API_KEY_ID — required, the key UUID from the Kalshi dashboard.

        Reads private key from pem_path (default: data/kalshi_private_key.pem).

        Raises:
            _KalshiCredentialError: if env var missing or PEM unreadable.
        """
        api_key_id = os.environ.get("KALSHI_API_KEY_ID", "")
        if not api_key_id:
            raise _KalshiCredentialError(
                "KALSHI_API_KEY_ID environment variable is not set. "
                "See docs/SETUP_GUIDE.md for Kalshi onboarding."
            )
        try:
            pem_bytes = pem_path.read_bytes()
        except OSError as exc:
            raise _KalshiCredentialError(
                f"Cannot read Kalshi private key from {pem_path}: {exc}. "
                "Generate an RSA key pair on the Kalshi dashboard and save "
                "the private key to data/kalshi_private_key.pem (gitignored)."
            ) from exc
        return cls(
            api_key_id=api_key_id,
            private_key_pem=pem_bytes,
            base_url=base_url,
            transport=transport,
        )

    # ------------------------------------------------------------------
    # RSA-PSS signing
    # ------------------------------------------------------------------

    def _load_signing_key(self) -> None:
        """Parse and cache the RSA private key from PEM bytes (lazy on first use)."""
        from cryptography.exceptions import UnsupportedAlgorithm
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

        if not self._private_key_pem:
            raise _KalshiSigningError(
                "private_key_pem is empty — cannot sign Kalshi requests. "
                "Provide a valid RSA PEM via from_env() or the constructor."
            )
        try:
            key = serialization.load_pem_private_key(self._private_key_pem, password=None)
        except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
            raise _KalshiSigningError(
                f"Cannot load RSA private key from PEM: {exc}. "
                "Check data/kalshi_private_key.pem is a valid RSA private key."
            ) from exc
        if not isinstance(key, RSAPrivateKey):
            raise _KalshiSigningError(
                f"PEM key is not RSA (got {type(key).__name__}). "
                "Kalshi requires RSA keypairs generated on the Kalshi dashboard."
            )
        self._signing_key = key

    def _sign_request(self, method: str, path: str, timestamp_ms: int) -> str:
        """Produce the base64-encoded RSA-PSS/SHA256 signature for one request.

        Signing string: f"{timestamp_ms}{method}{path}" (method uppercase).
        Algorithm: RSA-PSS, SHA-256 digest, SHA-256 MGF1, salt=DIGEST_LENGTH.

        Args:
            method: HTTP verb uppercase, e.g. "GET".
            path: full URL path including /trade-api/v2 prefix.
            timestamp_ms: millisecond epoch timestamp.

        Returns:
            Base64-encoded ASCII signature string.

        Raises:
            _KalshiSigningError: if PEM is invalid or signing fails.
        """
        if self._signing_key is None:
            self._load_signing_key()
        key = self._signing_key
        assert key is not None  # _load_signing_key raises on failure; never returns None

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        message = f"{timestamp_ms}{method}{path}".encode()
        try:
            sig: bytes = key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH,
                ),
                hashes.SHA256(),
            )
        except Exception as exc:  # noqa: BLE001
            raise _KalshiSigningError(f"RSA signing failed: {exc}") from exc
        return base64.b64encode(sig).decode("ascii")

    def _signing_headers(self, method: str, path: str) -> dict[str, str]:
        """Build Kalshi auth headers for a single request.

        Args:
            method: HTTP verb uppercase, e.g. "GET".
            path: full URL path including /trade-api/v2 prefix.

        Returns:
            Dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP,
            KALSHI-ACCESS-SIGNATURE, Content-Type, Accept.
        """
        ts_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        sig = self._sign_request(method, path, ts_ms)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": str(ts_ms),
            "KALSHI-ACCESS-SIGNATURE": sig,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    def _get_json(
        self,
        path_suffix: str,
        *,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], datetime]:
        """Make one signed GET request. Returns (json_body, received_at).

        Raises:
            _KalshiServerError: on 5xx (retried by tenacity).
            _KalshiAPIError: on 4xx (not retried).
            httpx.ConnectError / httpx.ReadTimeout: network failures (retried).
        """
        sign_path = f"{self._api_path_prefix}{path_suffix}"
        url = f"{self.base_url.rstrip('/')}{path_suffix}"
        headers = self._signing_headers("GET", sign_path)
        received_at = datetime.now(tz=UTC)
        with self._http() as http:
            resp = http.get(url, headers=headers, params=params)
        if resp.status_code >= 500:
            raise _KalshiServerError(resp.status_code, resp.text)
        if resp.status_code != 200:
            raise _KalshiAPIError(resp.status_code, resp.text)
        return resp.json(), received_at

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=DEFAULT_TIMEOUT, transport=self.transport)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, _KalshiServerError)),
        reraise=True,
    )
    def list_events(
        self,
        *,
        series_ticker: str = KXEPLTOTAL_SERIES,
        status: str = "open",
        limit: int = 100,
    ) -> KalshiResponse:
        """List open Kalshi events for a given series.

        Args:
            series_ticker: Kalshi series ticker, e.g. "KXEPLTOTAL".
            status: event status filter ("open", "closed", "settled").
            limit: max events to return.

        Returns:
            KalshiResponse with payload = list[KalshiEvent] from
            GET /events?series_ticker=...&status=...&limit=...
        """
        params = {
            "series_ticker": series_ticker,
            "status": status,
            "limit": str(limit),
        }
        body, received_at = self._get_json("/events", params=params)
        raw_events = body.get("events", [])
        events = [KalshiEvent.model_validate(e) for e in raw_events]
        return KalshiResponse(payload=events, received_at=received_at)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, _KalshiServerError)),
        reraise=True,
    )
    def list_markets(
        self,
        *,
        event_ticker: str,
        status: str = "open",
        limit: int = 100,
        floor_strike_filter: Decimal | None = None,
    ) -> KalshiResponse:
        """List markets for a specific event, optionally filtered by floor_strike.

        The floor_strike filter is applied client-side (Kalshi REST API does not
        expose a floor_strike query parameter).

        Args:
            event_ticker: e.g. "KXEPLTOTAL-26MAY24WHULEE".
            status: market status filter.
            limit: max markets to return.
            floor_strike_filter: if provided, only markets with
                floor_strike == floor_strike_filter are returned.

        Returns:
            KalshiResponse with payload = list[KalshiMarket] from
            GET /markets?event_ticker=...
        """
        params = {
            "event_ticker": event_ticker,
            "status": status,
            "limit": str(limit),
        }
        body, received_at = self._get_json("/markets", params=params)
        raw_markets = body.get("markets", [])
        markets = [KalshiMarket.model_validate(m) for m in raw_markets]
        if floor_strike_filter is not None:
            markets = [m for m in markets if m.floor_strike == floor_strike_filter]
        return KalshiResponse(payload=markets, received_at=received_at)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, _KalshiServerError)),
        reraise=True,
    )
    def get_market(self, ticker: str) -> KalshiResponse:
        """Get a single market by ticker.

        Args:
            ticker: Kalshi market ticker, e.g. "KXEPLTOTAL-26MAY24WHULEE-2".

        Returns:
            KalshiResponse with payload = KalshiMarket from
            GET /markets/<ticker>
        """
        body, received_at = self._get_json(f"/markets/{ticker}")
        market = KalshiMarket.model_validate(body["market"])
        return KalshiResponse(payload=market, received_at=received_at)


if __name__ == "__main__":
    # Smoke test: price helpers only (no network, no RSA)
    examples = [0.55, 0.40, 0.75, 0.20]
    for p in examples:
        odds = price_to_decimal_odds(p)
        roundtrip = decimal_odds_to_price(odds)
        print(f"  price={p:.2f} -> odds={odds:.4f} -> price_back={roundtrip:.2f}")
    print("smoke: price_to_decimal_odds / decimal_odds_to_price OK")

    # Smoke test: Pydantic model
    m = KalshiMarket(
        ticker="KXEPLTOTAL-26MAY24WHULEE-2",
        event_ticker="KXEPLTOTAL-26MAY24WHULEE",
        floor_strike="2.5",  # type: ignore[arg-type]
        yes_bid_dollars="0.5500",  # type: ignore[arg-type]
        no_bid_dollars="0.4500",  # type: ignore[arg-type]
    )
    print(f"  KalshiMarket: {m.ticker}, floor_strike={m.floor_strike}, yes_bid={m.yes_bid_dollars}")
    print("smoke: KalshiMarket model_validate OK")
