"""Kalshi Exchange client stub (Phase 3 step 5a).

RSA-PSS/SHA256 per-request signing is deferred to Phase 3 step 5b. Every
public method raises NotImplementedError so the paper-trader fails fast and
clearly rather than silently doing nothing.

Auth headers (step 5b will fill these in):
  KALSHI-ACCESS-KEY        — key ID from env var KALSHI_API_KEY_ID
  KALSHI-ACCESS-SIGNATURE  — base64(RSA-PSS-SHA256(timestamp + METHOD + path))
  KALSHI-ACCESS-TIMESTAMP  — millisecond epoch as string

Private PEM is expected at data/kalshi_private_key.pem (gitignored).
Key ID comes from env var KALSHI_API_KEY_ID.

Price convention: Kalshi prices are floats in [0.01, 0.99] representing
YES contract probability in dollars (e.g. 0.55 means 55 cents per dollar).
Use price_to_decimal_odds() / decimal_odds_to_price() for conversion.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_LOG = logging.getLogger(__name__)

DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"
PROD_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
DEFAULT_PEM_PATH = Path("data/kalshi_private_key.pem")

# Kalshi EPL total goals series ticker
KXEPLTOTAL_SERIES = "KXEPLTOTAL"


class _KalshiCredentialError(Exception):
    """Raised at client init when required credentials are missing or unreadable."""


@dataclass(frozen=True)
class KalshiResponse:
    """Wraps a Kalshi API payload with our wall-clock receipt timestamp.

    Mirrors BetfairResponse so the orchestration layer can treat both
    venue responses uniformly.
    """

    payload: Any
    received_at: datetime
    source_timestamp: datetime | None = None
    staleness_seconds: int = 0


def price_to_decimal_odds(yes_bid_dollars: float) -> float:
    """Convert a Kalshi YES bid price to decimal odds.

    Args:
        yes_bid_dollars: Kalshi yes_bid_dollars field, a float in [0.01, 0.99].
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


def _sign_request(
    private_key_pem: bytes,
    method: str,
    path: str,
    timestamp_ms: int,
) -> str:
    """Produce the base64-encoded RSA-PSS/SHA256 signature for a Kalshi request.

    Signing string: f"{timestamp_ms}{METHOD}{path}"
    Algorithm: RSA-PSS, SHA-256 digest, SHA-256 MGF.

    NOTE (Phase 3 step 5a): this function body raises NotImplementedError.
    Step 5b wires the actual cryptography call here.

    Args:
        private_key_pem: raw bytes of the PEM-encoded RSA private key.
        method: HTTP verb uppercase, e.g. "GET".
        path: URL path without host, e.g. "/trade-api/v2/events".
        timestamp_ms: millisecond epoch timestamp.

    Returns:
        Base64-encoded signature string for the KALSHI-ACCESS-SIGNATURE header.
    """
    raise NotImplementedError(
        "Kalshi RSA-PSS signing not yet implemented; see Phase 3 step 5b. "
        "Install cryptography>=42 and implement using "
        "cryptography.hazmat.primitives.asymmetric.padding.PSS."
    )
    # Step 5b implementation outline:
    #   from cryptography.hazmat.primitives import hashes, serialization
    #   from cryptography.hazmat.primitives.asymmetric import padding
    #   private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    #   message = f"{timestamp_ms}{method.upper()}{path}".encode()
    #   sig = private_key.sign(message, padding.PSS(
    #       mgf=padding.MGF1(hashes.SHA256()),
    #       salt_length=padding.PSS.MAX_LENGTH,
    #   ), hashes.SHA256())
    #   return base64.b64encode(sig).decode()
    _ = private_key_pem, method, path, timestamp_ms, base64  # noqa: F841


@dataclass
class KalshiClient:
    """Kalshi Exchange API client stub.

    All public methods raise NotImplementedError (Phase 3 step 5a). The
    scaffolding (auth header construction, tenacity retry decorators, response
    dataclass) is wired so step 5b only needs to fill in the HTTP call bodies.

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

    def __post_init__(self) -> None:
        self._private_key_pem = self.private_key_pem

    @classmethod
    def from_env(
        cls,
        *,
        pem_path: Path = DEFAULT_PEM_PATH,
        base_url: str = PROD_BASE_URL,
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
        return cls(api_key_id=api_key_id, private_key_pem=pem_bytes, base_url=base_url)

    # ------------------------------------------------------------------
    # Auth header construction (step 5b wires the real signature here)
    # ------------------------------------------------------------------
    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Build Kalshi auth headers for a single request.

        Raises NotImplementedError until step 5b fills in _sign_request().
        """
        ts_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        sig = _sign_request(self._private_key_pem, method, path, ts_ms)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": str(ts_ms),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Public API methods (all stub out to NotImplementedError)
    # ------------------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def get_events(
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
            limit: max events to return (API max varies by tier).

        Returns:
            KalshiResponse with payload = list of event dicts from
            GET /trade-api/v2/events?series_ticker=...

        Raises:
            NotImplementedError: until Phase 3 step 5b.
        """
        raise NotImplementedError("Kalshi RSA auth not yet implemented; see Phase 3 step 5b")
        _ = series_ticker, status, limit  # noqa: F841

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def get_markets(
        self,
        *,
        event_ticker: str,
        status: str = "open",
    ) -> KalshiResponse:
        """List markets for a specific event.

        Args:
            event_ticker: e.g. "kxepltotal-26may01leebur".
            status: market status filter.

        Returns:
            KalshiResponse with payload = list of market dicts from
            GET /trade-api/v2/markets?event_ticker=...

        Raises:
            NotImplementedError: until Phase 3 step 5b.
        """
        raise NotImplementedError("Kalshi RSA auth not yet implemented; see Phase 3 step 5b")
        _ = event_ticker, status  # noqa: F841

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def get_market_orderbook(
        self,
        *,
        ticker: str,
        depth: int = 1,
    ) -> KalshiResponse:
        """Get order book depth for a single market ticker.

        Args:
            ticker: Kalshi market ticker (e.g. "KXEPLTOTAL-26MAY01LEEBUR-T2.5").
            depth: number of price levels to return.

        Returns:
            KalshiResponse with payload = order book dict including
            yes_bid_dollars, yes_ask_dollars, no_bid_dollars, no_ask_dollars,
            volume_fp, open_interest_fp, yes_bid_size_fp, yes_ask_size_fp.

        Raises:
            NotImplementedError: until Phase 3 step 5b.
        """
        raise NotImplementedError("Kalshi RSA auth not yet implemented; see Phase 3 step 5b")
        _ = ticker, depth  # noqa: F841

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=DEFAULT_TIMEOUT, transport=self.transport)


if __name__ == "__main__":
    # Smoke test: price helpers only (no network, no RSA)
    examples = [0.55, 0.40, 0.75, 0.20]
    for p in examples:
        odds = price_to_decimal_odds(p)
        roundtrip = decimal_odds_to_price(odds)
        print(f"  price={p:.2f} → odds={odds:.4f} → price_back={roundtrip:.2f}")
    print("smoke: price_to_decimal_odds / decimal_odds_to_price OK")
