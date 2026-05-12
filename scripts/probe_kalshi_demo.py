"""probe_kalshi_demo.py — one-off shape discovery against Kalshi demo endpoint.

DEMO-ONLY. Refuses to run if KALSHI_API_BASE_URL does not contain 'demo'.

Usage:
    $env:KALSHI_API_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"
    $env:KALSHI_API_KEY_ID   = "<your-key-id>"
    # PEM at data/kalshi_private_key.pem  (default path)
    uv run python scripts/probe_kalshi_demo.py

Output:
  - Pretty-printed JSON for each endpoint
  - Discovered-fields summary (ticker patterns, price field names)
  - Clock skew check vs Kalshi Date header
  - Capture file written to tests/fixtures/kalshi_demo_capture_<ts>.json

The capture file is .gitignored. Paste its contents back into chat for the
5b-implementation session where parsers get locked to real shapes.
"""

from __future__ import annotations

import email.utils
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Bootstrap project path so footy_ev is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_PROJECT_ROOT / ".env")

from footy_ev.venues.kalshi import (  # noqa: E402
    DEMO_BASE_URL,
    KalshiClient,
    _KalshiCredentialError,
    _KalshiSigningError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
KXEPLTOTAL_SERIES = "KXEPLTOTAL"
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=5.0)
CLOCK_SKEW_LIMIT_SEC = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_clock_skew(response: httpx.Response, label: str) -> None:
    """Print a warning if the server Date header drifts > 30s from local UTC."""
    date_hdr = response.headers.get("Date", "")
    if not date_hdr:
        print(f"  [clock] No Date header from {label} — cannot check skew")
        return
    try:
        remote_dt = email.utils.parsedate_to_datetime(date_hdr)
        drift = abs(remote_dt.timestamp() - time.time())
        if drift > CLOCK_SKEW_LIMIT_SEC:
            print(
                f"  !! CLOCK SKEW WARNING: {drift:.1f}s drift on {label}. "
                f"RSA auth will fail if drift > {CLOCK_SKEW_LIMIT_SEC}s. "
                "Sync your system clock (NTP)."
            )
        else:
            print(f"  [clock] {label}: clock drift {drift:.1f}s (OK)")
    except Exception as exc:  # noqa: BLE001
        print(f"  [clock] Could not parse Date header from {label}: {exc}")


def _summarise_fields(payload: object, indent: str = "  ") -> None:
    """Print discovered field names and patterns from a JSON payload."""
    if isinstance(payload, dict):
        print(f"{indent}Top-level keys: {list(payload.keys())}")
        # Look for nested lists and print their item keys
        for k, v in payload.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                sample = v[0]
                print(f"{indent}  [{k}] item keys: {list(sample.keys())}")
                _print_price_fields(sample, indent + "    ")
                _print_ticker_patterns(v, k, indent + "    ")
    elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
        print(f"{indent}List of dicts, item keys: {list(payload[0].keys())}")
        _print_price_fields(payload[0], indent + "  ")
        _print_ticker_patterns(payload, "root", indent + "  ")


def _print_price_fields(obj: dict[str, object], indent: str) -> None:
    """Highlight price-related fields found in a market/orderbook dict."""
    price_keywords = ("bid", "ask", "price", "settlement", "volume", "interest")
    price_fields = [k for k in obj if any(kw in k.lower() for kw in price_keywords)]
    if price_fields:
        print(f"{indent}Price-related fields: {price_fields}")
        for f in price_fields:
            print(f"{indent}  {f!r}: {obj[f]!r}")


def _print_ticker_patterns(items: list[object], label: str, indent: str) -> None:
    """Show unique ticker suffix patterns (e.g. -T1.5, -T2.5, -T3.5)."""
    tickers: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for key in ("ticker", "event_ticker", "series_ticker"):
                val = item.get(key)
                if isinstance(val, str):
                    tickers.append(f"{key}={val}")
    if tickers:
        print(f"{indent}Tickers in [{label}]: {tickers[:10]}")


def _get(
    client: KalshiClient,
    base_url: str,
    path_suffix: str,
    *,
    params: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], object]:
    """Make one authenticated GET and return (status, headers_dict, payload)."""
    url = base_url.rstrip("/") + path_suffix
    parsed = urlparse(base_url)
    api_path_prefix = parsed.path.rstrip("/")
    # Build path for signing: prefix + suffix (strips query string)
    sign_path = api_path_prefix + path_suffix.split("?")[0]

    headers = client._signing_headers("GET", sign_path)
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
    except httpx.HTTPError as exc:
        print(f"  HTTP error for {path_suffix}: {exc}")
        return -1, {}, {}

    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        payload = {"_raw_text": resp.text[:500]}

    return resp.status_code, dict(resp.headers), payload


# ---------------------------------------------------------------------------
# Main probe logic
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: PLR0912, PLR0915
    base_url = os.environ.get("KALSHI_API_BASE_URL", DEMO_BASE_URL)
    if "demo" not in base_url.lower():
        print(f"ERROR: KALSHI_API_BASE_URL must contain 'demo'. Got: {base_url!r}")
        print("This probe is DEMO-ONLY and refuses to run against production.")
        return 1

    print(f"Probe target: {base_url}")
    print(f"Timestamp: {datetime.now(tz=UTC).isoformat()}")
    print()

    # Build client
    pem_path = Path(
        os.environ.get("KALSHI_PEM_PATH", str(_PROJECT_ROOT / "data/kalshi_private_key.pem"))
    )
    try:
        client = KalshiClient.from_env(pem_path=pem_path, base_url=base_url)
    except _KalshiCredentialError as exc:
        print(f"Credential error: {exc}")
        return 1

    # Verify signing works before any network calls
    try:
        _ = client._signing_headers("GET", "/trade-api/v2/series")
    except _KalshiSigningError as exc:
        print(f"Signing error: {exc}")
        return 1
    print("RSA signing: OK")
    print()

    captured: list[dict[str, object]] = []
    success = True

    # ------------------------------------------------------------------
    # Call 1: GET /series — confirm KXEPLTOTAL exists in catalog
    # ------------------------------------------------------------------
    print("=" * 60)
    print("CALL 1: GET /series")
    print("=" * 60)
    status, hdrs, payload = _get(client, base_url, "/series")
    print(f"Status: {status}")
    _check_clock_skew(
        httpx.Response(status, headers=hdrs),
        "/series",
    )
    if status == 200:
        print("Fields discovered:")
        _summarise_fields(payload)
        if isinstance(payload, dict):
            series_list = payload.get("series", payload.get("data", []))
            if isinstance(series_list, list):
                tickers = [
                    s.get("ticker", s.get("series_ticker", "?"))
                    for s in series_list
                    if isinstance(s, dict)
                ]
                print(f"  Series tickers: {tickers[:20]}")
                if KXEPLTOTAL_SERIES in tickers:
                    print(f"  ✓ {KXEPLTOTAL_SERIES} found in series catalog")
                else:
                    print(f"  ✗ {KXEPLTOTAL_SERIES} NOT found. Available: {tickers}")
    else:
        print(f"Response body: {json.dumps(payload, indent=2, default=str)[:500]}")
        success = False
    captured.append({"path": "/series", "method": "GET", "status": status, "payload": payload})
    print()

    # ------------------------------------------------------------------
    # Call 2: GET /events?series_ticker=KXEPLTOTAL&status=open&limit=5
    # ------------------------------------------------------------------
    print("=" * 60)
    print(f"CALL 2: GET /events?series_ticker={KXEPLTOTAL_SERIES}&status=open&limit=5")
    print("=" * 60)
    events_path = "/events"
    events_params = {"series_ticker": KXEPLTOTAL_SERIES, "status": "open", "limit": "5"}
    status2, hdrs2, payload2 = _get(client, base_url, events_path, params=events_params)
    print(f"Status: {status2}")
    _check_clock_skew(
        httpx.Response(status2, headers=hdrs2),
        "/events",
    )

    first_event_ticker: str | None = None
    if status2 == 200:
        print("Fields discovered:")
        _summarise_fields(payload2)
        events_list: list[object] = []
        if isinstance(payload2, dict):
            raw_ev = payload2.get("events", payload2.get("data", []))
            if isinstance(raw_ev, list):
                events_list = list(raw_ev)
        elif isinstance(payload2, list):
            events_list = payload2
        if events_list:
            first = events_list[0]
            if isinstance(first, dict):
                first_event_ticker = first.get("event_ticker") or first.get("ticker")
                print(f"  First event_ticker: {first_event_ticker!r}")
                print(f"  Full first event: {json.dumps(first, indent=4, default=str)}")
        else:
            print(f"  ✗ No open {KXEPLTOTAL_SERIES} events on demo (EPL off-season?).")
            print("    That's useful intel — captured for record.")
    else:
        print(f"Response: {json.dumps(payload2, indent=2, default=str)[:500]}")
        success = False
    captured.append(
        {
            "path": f"/events?series_ticker={KXEPLTOTAL_SERIES}&status=open&limit=5",
            "method": "GET",
            "status": status2,
            "payload": payload2,
        }
    )
    print()

    # ------------------------------------------------------------------
    # Call 3: GET /markets?event_ticker=<first>&limit=20
    # ------------------------------------------------------------------
    print("=" * 60)
    print("CALL 3: GET /markets?event_ticker=<first_event>&limit=20")
    print("=" * 60)
    first_market_ticker: str | None = None
    if first_event_ticker:
        markets_params = {"event_ticker": first_event_ticker, "limit": "20"}
        status3, hdrs3, payload3 = _get(client, base_url, "/markets", params=markets_params)
        print(f"Status: {status3}")
        _check_clock_skew(
            httpx.Response(status3, headers=hdrs3),
            "/markets",
        )
        if status3 == 200:
            print("Fields discovered:")
            _summarise_fields(payload3)
            markets_list: list[object] = []
            if isinstance(payload3, dict):
                raw_mkt = payload3.get("markets", payload3.get("data", []))
                if isinstance(raw_mkt, list):
                    markets_list = list(raw_mkt)
            elif isinstance(payload3, list):
                markets_list = payload3
            if markets_list:
                first_mkt = markets_list[0]
                if isinstance(first_mkt, dict):
                    first_market_ticker = first_mkt.get("ticker")
                    print(f"  First market ticker: {first_market_ticker!r}")
                # Print all tickers to reveal threshold variety
                all_tickers = [m.get("ticker", "?") for m in markets_list if isinstance(m, dict)]
                print(f"  All market tickers under {first_event_ticker!r}: {all_tickers}")
                print(f"  Full first market: {json.dumps(first_mkt, indent=4, default=str)}")
        else:
            print(f"Response: {json.dumps(payload3, indent=2, default=str)[:500]}")
            success = False
        captured.append(
            {
                "path": f"/markets?event_ticker={first_event_ticker}&limit=20",
                "method": "GET",
                "status": status3,
                "payload": payload3,
            }
        )
    else:
        print("Skipped — no event ticker from Call 2")
        captured.append(
            {"path": "/markets (skipped)", "method": "GET", "status": 0, "payload": None}
        )
    print()

    # ------------------------------------------------------------------
    # Call 4: GET /markets/<ticker> — single market detail
    # ------------------------------------------------------------------
    print("=" * 60)
    print("CALL 4: GET /markets/<first_market_ticker>")
    print("=" * 60)
    if first_market_ticker:
        mkt_path = f"/markets/{first_market_ticker}"
        status4, hdrs4, payload4 = _get(client, base_url, mkt_path)
        print(f"Status: {status4}")
        _check_clock_skew(
            httpx.Response(status4, headers=hdrs4),
            mkt_path,
        )
        if status4 == 200:
            print("Fields discovered:")
            _summarise_fields(payload4)
            mkt_obj = payload4.get("market", payload4) if isinstance(payload4, dict) else payload4
            print(f"  Full single-market response: {json.dumps(mkt_obj, indent=4, default=str)}")
        else:
            print(f"Response: {json.dumps(payload4, indent=2, default=str)[:500]}")
            success = False
        captured.append({"path": mkt_path, "method": "GET", "status": status4, "payload": payload4})
    else:
        print("Skipped — no market ticker from Call 3")
        captured.append(
            {"path": "/markets/<ticker> (skipped)", "method": "GET", "status": 0, "payload": None}
        )
    print()

    # ------------------------------------------------------------------
    # Write capture file
    # ------------------------------------------------------------------
    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    capture_path = _PROJECT_ROOT / "tests" / "fixtures" / f"kalshi_demo_capture_{ts}.json"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_doc = {
        "captured_at": datetime.now(tz=UTC).isoformat(),
        "base_url": base_url,
        "endpoints": captured,
    }
    capture_path.write_text(json.dumps(capture_doc, indent=2, default=str), encoding="utf-8")
    print(f"Capture written to: {capture_path}")
    print("Paste the contents of that file back into chat for 5b-implementation.")
    print()

    if not success:
        print("One or more calls returned non-200. Check errors above.")
        return 1

    print("Probe complete — all calls succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
