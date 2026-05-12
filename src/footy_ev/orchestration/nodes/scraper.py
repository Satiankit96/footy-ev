"""Scraper node — pulls odds from Kalshi, resolves events to fixture_ids."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import duckdb

from footy_ev.orchestration.state import BettingState, MarketType, OddsSnapshot
from footy_ev.venues.kalshi import (
    OU25_FLOOR_STRIKE,
    KalshiClient,
    KalshiMarket,
    price_to_decimal_odds,
)
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

    Two-call flow per event:
    1. list_events(series_ticker="KXEPLTOTAL") → event tickers
    2. list_markets(event_ticker=..., floor_strike_filter=2.5) → OU 2.5 market

    Unresolved events are dropped. More than RESOLUTION_FAILURE_THRESHOLD
    fraction failing trips the circuit breaker.

    Args:
        state: current BettingState.
        client: authenticated KalshiClient.
        con: warehouse connection. Required for entity resolution.
    """
    try:
        events_resp = client.list_events(series_ticker="KXEPLTOTAL")
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
            "breaker_reason": f"Kalshi list_events failed: {type(exc).__name__}: {exc}",
        }

    events = events_resp.payload if isinstance(events_resp.payload, list) else []
    new_snapshots: list[OddsSnapshot] = []
    resolved_fixture_ids: list[str] = []
    freshness: dict[str, int] = {}
    resolution_attempts = 0
    resolution_failures = 0

    for event in events:
        # Support both KalshiEvent objects and raw dicts (test compatibility)
        if hasattr(event, "event_ticker"):
            event_ticker = str(event.event_ticker)
        else:
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

        # Fetch OU 2.5 market for this event
        try:
            markets_resp = client.list_markets(
                event_ticker=event_ticker,
                floor_strike_filter=OU25_FLOOR_STRIKE,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("scraper[kalshi]: list_markets failed for %s: %s", event_ticker, exc)
            if con is not None:
                resolution_failures += 1
            continue

        markets = markets_resp.payload if isinstance(markets_resp.payload, list) else []
        for market in markets:
            snaps = _extract_kalshi_snapshot(market, fixture_id, events_resp.received_at)
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
    market: KalshiMarket,
    fixture_id: str,
    captured_at: datetime,
) -> list[OddsSnapshot]:
    """Build OddsSnapshots (over + under) from one Kalshi market.

    Reads yes_bid_dollars / no_bid_dollars (Decimal, parsed from 4-decimal
    strings like "0.5500"). Returns empty list when prices are absent or
    outside the tradeable range (0, 1) exclusive — e.g. "0.0000" no-bid.

    Args:
        market: parsed KalshiMarket from the REST API.
        fixture_id: warehouse fixture identifier.
        captured_at: wall-clock time the events list was received.

    Returns:
        List of OddsSnapshot (0, 1, or 2 elements).
    """
    yes_bid = market.yes_bid_dollars
    no_bid = market.no_bid_dollars

    _ZERO = Decimal("0")
    _ONE = Decimal("1")

    snapshots: list[OddsSnapshot] = []

    if _ZERO < yes_bid < _ONE:
        try:
            yes_odds = price_to_decimal_odds(float(yes_bid))
            snapshots.append(
                OddsSnapshot(
                    venue="kalshi",
                    fixture_id=fixture_id,
                    market=MarketType.OU_25,
                    selection=_KALSHI_YES_SELECTION,
                    odds_decimal=yes_odds,
                    captured_at=captured_at.astimezone(UTC),
                    staleness_seconds=0,
                    liquidity_gbp=market.yes_bid_size_fp or None,
                )
            )
        except (ValueError, ZeroDivisionError):
            pass
    else:
        _LOG.debug(
            "scraper[kalshi]: market %s has no active yes_bid (%s) — over snapshot skipped",
            market.ticker,
            yes_bid,
        )

    if _ZERO < no_bid < _ONE:
        try:
            no_odds = price_to_decimal_odds(float(no_bid))
            snapshots.append(
                OddsSnapshot(
                    venue="kalshi",
                    fixture_id=fixture_id,
                    market=MarketType.OU_25,
                    selection=_KALSHI_NO_SELECTION,
                    odds_decimal=no_odds,
                    captured_at=captured_at.astimezone(UTC),
                    staleness_seconds=0,
                    liquidity_gbp=None,  # no_bid_size not exposed by Kalshi REST API
                )
            )
        except (ValueError, ZeroDivisionError):
            pass
    else:
        _LOG.debug(
            "scraper[kalshi]: market %s has no active no_bid (%s) — under snapshot skipped",
            market.ticker,
            no_bid,
        )

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
