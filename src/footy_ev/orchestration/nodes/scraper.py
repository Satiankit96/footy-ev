"""Scraper node — pulls odds from Kalshi, resolves events to fixture_ids."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import duckdb

from footy_ev.orchestration.state import BettingState, MarketType, OddsSnapshot
from footy_ev.venues.kalshi import KalshiClient, price_to_decimal_odds
from footy_ev.venues.resolution import cache_kalshi_resolution, resolve_kalshi_market

_LOG = logging.getLogger(__name__)

# Kalshi: YES contract = over the threshold for total goals markets.
_KALSHI_YES_SELECTION = "over"
_KALSHI_NO_SELECTION = "under"

# If this fraction of events fail to resolve, the circuit breaker trips.
_RESOLUTION_FAILURE_THRESHOLD = 0.5


def scraper_node(
    state: BettingState,
    *,
    client: KalshiClient,
    con: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Pull odds from Kalshi and resolve events to warehouse fixture_ids.

    Calls client.get_events() for KXEPLTOTAL series, then for each event
    calls client.get_market_orderbook() and resolves the event ticker to a
    warehouse fixture_id via kalshi_event_aliases. Unresolved events are
    dropped. More than RESOLUTION_FAILURE_THRESHOLD fraction failing trips
    the circuit breaker.

    Args:
        state: current BettingState.
        client: authenticated KalshiClient.
        con: warehouse connection. Required for entity resolution.
    """
    try:
        resp = client.get_events(series_ticker="KXEPLTOTAL")
    except NotImplementedError as exc:
        return {
            "odds_snapshots": [],
            "resolved_fixture_ids": [],
            "data_freshness_seconds": {},
            "circuit_breaker_tripped": True,
            "breaker_reason": (
                f"KalshiClient not yet implemented: {exc}. "
                "Complete Phase 3 step 5b to wire RSA-PSS auth."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "odds_snapshots": [],
            "resolved_fixture_ids": [],
            "data_freshness_seconds": {},
            "circuit_breaker_tripped": True,
            "breaker_reason": f"Kalshi get_events failed: {type(exc).__name__}: {exc}",
        }

    events: list[dict[str, Any]] = resp.payload if isinstance(resp.payload, list) else []
    new_snapshots: list[OddsSnapshot] = []
    resolved_fixture_ids: list[str] = []
    freshness: dict[str, int] = {}
    resolution_attempts = 0
    resolution_failures = 0

    for event in events:
        event_ticker = str(event.get("event_ticker", ""))
        if not event_ticker:
            continue

        if con is not None:
            resolution_attempts += 1
            res = resolve_kalshi_market(con, event_ticker)
            _cache_kalshi_resolution_safe(con, event_ticker, res)
            if res.status != "resolved" or not res.fixture_id:
                resolution_failures += 1
                _LOG.info("scraper[kalshi]: event %s unresolved: %s", event_ticker, res.reason)
                continue
            fixture_id = res.fixture_id
            resolved_fixture_ids.append(fixture_id)
        else:
            fixture_id = event_ticker  # fallback when no warehouse connection

        for market in event.get("markets", []):
            snaps = _extract_kalshi_snapshot(market, fixture_id, resp.received_at)
            if snaps:
                new_snapshots.extend(snaps)
                freshness[f"kalshi:{fixture_id}"] = 0

    breaker_tripped = False
    breaker_reason = ""
    if (
        resolution_attempts > 0
        and resolution_failures / resolution_attempts > _RESOLUTION_FAILURE_THRESHOLD
    ):
        fail_pct = int(100 * resolution_failures / resolution_attempts)
        breaker_tripped = True
        breaker_reason = (
            f"unresolved_event: {resolution_failures}/{resolution_attempts} Kalshi events "
            f"({fail_pct}%) failed resolution. "
            "Run scripts/bootstrap_kalshi_aliases.py --from-fixture to populate kalshi_event_aliases."
        )
        _LOG.warning("scraper[kalshi]: %s", breaker_reason)

    out: dict[str, Any] = {
        "odds_snapshots": new_snapshots,
        "resolved_fixture_ids": resolved_fixture_ids,
        "data_freshness_seconds": freshness,
        "circuit_breaker_tripped": breaker_tripped,
    }
    if breaker_tripped:
        out["breaker_reason"] = breaker_reason
    return out


def _extract_kalshi_snapshot(
    market: dict[str, Any],
    fixture_id: str,
    captured_at: datetime,
) -> list[OddsSnapshot]:
    """Build OddsSnapshots (over + under) from one Kalshi market dict.

    Reads yes_bid_dollars / no_bid_dollars (string cents, e.g. "0.5500").
    Returns empty list when fields are absent or prices are out of range.
    """
    yes_bid = market.get("yes_bid_dollars")
    no_bid = market.get("no_bid_dollars")
    if yes_bid is None or no_bid is None:
        return []
    try:
        yes_bid_f = float(yes_bid)
        no_bid_f = float(no_bid)
    except (TypeError, ValueError):
        return []
    if not (0.0 < yes_bid_f < 1.0) or not (0.0 < no_bid_f < 1.0):
        return []

    yes_size = market.get("yes_bid_size_fp")
    no_size = market.get("no_bid_size_fp")

    snapshots: list[OddsSnapshot] = []
    try:
        yes_odds = price_to_decimal_odds(yes_bid_f)
        snapshots.append(
            OddsSnapshot(
                venue="kalshi",
                fixture_id=fixture_id,
                market=MarketType.OU_25,
                selection=_KALSHI_YES_SELECTION,
                odds_decimal=yes_odds,
                captured_at=captured_at.astimezone(UTC),
                staleness_seconds=0,
                liquidity_gbp=float(yes_size) if yes_size is not None else None,
            )
        )
    except (ValueError, ZeroDivisionError):
        pass
    try:
        no_odds = price_to_decimal_odds(no_bid_f)
        snapshots.append(
            OddsSnapshot(
                venue="kalshi",
                fixture_id=fixture_id,
                market=MarketType.OU_25,
                selection=_KALSHI_NO_SELECTION,
                odds_decimal=no_odds,
                captured_at=captured_at.astimezone(UTC),
                staleness_seconds=0,
                liquidity_gbp=float(no_size) if no_size is not None else None,
            )
        )
    except (ValueError, ZeroDivisionError):
        pass

    return snapshots


def _cache_kalshi_resolution_safe(
    con: duckdb.DuckDBPyConnection,
    event_ticker: str,
    res: Any,
) -> None:
    try:
        cache_kalshi_resolution(con, event_ticker, res)
    except Exception:  # noqa: BLE001
        _LOG.debug("scraper: could not cache Kalshi resolution for %s", event_ticker)
