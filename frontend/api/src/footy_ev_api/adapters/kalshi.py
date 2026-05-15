"""Thin adapter around the existing KalshiClient.

Translates KalshiClient exceptions into AppError codes and provides
credential-check + health-check helpers that never leak secrets.
"""

from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from footy_ev_api.errors import AppError

_LOG = logging.getLogger(__name__)

_KALSHI_ERRORS = {
    "CredentialError": ("KALSHI_NOT_CONFIGURED", 503),
    "SigningError": ("KALSHI_AUTH_FAILED", 502),
    "ServerError": ("KALSHI_SERVER_ERROR", 502),
    "APIError": ("KALSHI_API_ERROR", 502),
    "ConnectError": ("KALSHI_TIMEOUT", 504),
    "ReadTimeout": ("KALSHI_TIMEOUT", 504),
}


def _translate_exception(exc: Exception) -> AppError:
    """Map a KalshiClient exception to an AppError."""
    cls_name = type(exc).__name__
    for suffix, (code, status) in _KALSHI_ERRORS.items():
        if suffix in cls_name:
            return AppError(code, str(exc), status)
    return AppError("KALSHI_ERROR", str(exc), 502)


def get_kalshi_client() -> Any:
    """Return a KalshiClient from env. Raises AppError if not configured."""
    try:
        from footy_ev.venues.kalshi import KalshiClient

        base_url = os.environ.get("KALSHI_API_BASE_URL", "")
        kwargs: dict[str, Any] = {}
        if base_url:
            kwargs["base_url"] = base_url
        return KalshiClient.from_env(**kwargs)
    except Exception as exc:
        raise _translate_exception(exc) from exc


def credentials_status() -> dict[str, Any]:
    """Check whether Kalshi credentials are configured. Never returns secret values."""
    key_id = os.environ.get("KALSHI_API_KEY_ID", "")
    key_path_str = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "data/kalshi_private_key.pem")
    base_url = os.environ.get("KALSHI_API_BASE_URL", "")
    key_path = Path(key_path_str) if key_path_str else Path("data/kalshi_private_key.pem")
    pk_exists = key_path.exists()
    return {
        "configured": bool(key_id and pk_exists and base_url),
        "key_id_present": bool(key_id),
        "private_key_present": pk_exists,
        "base_url": base_url,
        "is_demo": "demo" in base_url.lower(),
    }


def check_health(client: Any) -> dict[str, Any]:
    """Ping Kalshi API, measure latency, check clock skew."""
    import httpx

    base_url: str = client.base_url
    start = time.monotonic()
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        ) as http:
            resp = http.get(
                f"{base_url.rstrip('/')}/series", headers={"Accept": "application/json"}
            )
        latency_ms = round((time.monotonic() - start) * 1000, 1)

        clock_skew_s: float | None = None
        date_header = resp.headers.get("date")
        if date_header:
            from datetime import UTC, datetime
            from email.utils import parsedate_to_datetime

            try:
                server_time = parsedate_to_datetime(date_header).replace(tzinfo=UTC)
                local_time = datetime.now(UTC)
                clock_skew_s = round(abs((local_time - server_time).total_seconds()), 1)
            except Exception:
                clock_skew_s = None

        return {
            "ok": resp.status_code < 400,
            "latency_ms": latency_ms,
            "clock_skew_s": clock_skew_s,
            "base_url": base_url,
            "error": None if resp.status_code < 400 else f"HTTP {resp.status_code}",
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "clock_skew_s": None,
            "base_url": base_url,
            "error": str(exc),
        }


def list_events(
    client: Any, *, series_ticker: str = "KXEPLTOTAL", status: str = "open", limit: int = 100
) -> list[Any]:
    """List events via the KalshiClient, translating errors."""
    try:
        resp = client.list_events(series_ticker=series_ticker, status=status, limit=limit)
        return resp.payload  # type: ignore[no-any-return]
    except Exception as exc:
        raise _translate_exception(exc) from exc


def list_markets(client: Any, *, event_ticker: str, status: str = "open") -> list[Any]:
    """List markets for an event via the KalshiClient."""
    try:
        resp = client.list_markets(event_ticker=event_ticker, status=status)
        return resp.payload  # type: ignore[no-any-return]
    except Exception as exc:
        raise _translate_exception(exc) from exc


def get_market(client: Any, ticker: str) -> Any:
    """Get a single market by ticker."""
    try:
        resp = client.get_market(ticker)
        return resp.payload
    except Exception as exc:
        raise _translate_exception(exc) from exc


def compute_decimal_odds(yes_bid: Decimal) -> str | None:
    """Compute decimal odds from yes_bid. Returns string or None if zero."""
    if yes_bid <= 0:
        return None
    return str(round(Decimal("1") / yes_bid, 4))


def compute_implied_probability(yes_bid: Decimal) -> str | None:
    """Compute implied probability percentage from yes_bid."""
    if yes_bid <= 0:
        return None
    return str(round(yes_bid * 100, 2))
