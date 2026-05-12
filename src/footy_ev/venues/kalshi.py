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


class _KalshiSigningError(Exception):
    """Raised when RSA signing fails (corrupted PEM, non-RSA key, runtime error)."""


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
    _signing_key: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._private_key_pem = self.private_key_pem
        # _signing_key is loaded lazily on first _sign_request call so that
        # clients constructed with stub/test PEM bytes don't fail at init.

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
    # RSA-PSS signing (Phase 3 step 5b implementation)
    # ------------------------------------------------------------------

    def _load_signing_key(self) -> None:
        """Parse and cache the RSA private key from PEM bytes.

        Called lazily by _sign_request on first use. Raises
        _KalshiSigningError for corrupt PEM, empty bytes, or non-RSA keys.
        """
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

        Path is the full URL path including /trade-api/v2 prefix. The probe
        script confirms whether Kalshi's demo endpoint agrees with this
        assumption; adjust if discovery shows a shorter path is expected.

        Args:
            method: HTTP verb uppercase, e.g. "GET".
            path: full URL path, e.g. "/trade-api/v2/events".
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

        Returns the three required Kalshi-specific headers plus Content-Type
        and Accept. Use this with raw httpx calls; the stub public methods
        (get_events etc.) still raise NotImplementedError until 5b-implementation.

        Args:
            method: HTTP verb uppercase, e.g. "GET".
            path: full URL path including /trade-api/v2 prefix.

        Returns:
            Dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP,
            KALSHI-ACCESS-SIGNATURE, Content-Type, Accept.

        Raises:
            _KalshiSigningError: if signing fails.
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
    # Public API methods (bodies still raise NotImplementedError — 5b-impl)
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
