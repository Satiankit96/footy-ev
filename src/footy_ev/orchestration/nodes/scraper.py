"""Scraper node — pulls odds from the configured venue, resolves events to fixture_ids.

Supported venues:
  "betfair_exchange"  — BetfairClient (BLUE_MAP §5, deprecated for US operator)
  "kalshi"            — KalshiClient stub (Phase 3 step 5a; step 5b wires real auth)

The venue parameter selects which client + resolver path runs. Betfair remains
importable for backward compat but the default has changed to "kalshi".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

import duckdb

from footy_ev.orchestration.state import BettingState, MarketType, OddsSnapshot
from footy_ev.venues import BetfairClient, KalshiClient
from footy_ev.venues.resolution import (
    EventResolution,
    cache_kalshi_resolution,
    cache_resolution,
    resolve_event_from_meta,
    resolve_kalshi_market,
)

_LOG = logging.getLogger(__name__)
STALENESS_LIMIT_SEC = 300

# Betfair Selection ID lookup — Phase 3 step 1 handles OU 2.5 only.
_OU25_SELECTION_BY_ID: dict[int, str] = {1: "over", 2: "under"}

# Kalshi: YES contract = over the threshold for total goals markets.
_KALSHI_YES_SELECTION = "over"
_KALSHI_NO_SELECTION = "under"

# If this fraction of events fail to resolve, the circuit breaker trips.
_RESOLUTION_FAILURE_THRESHOLD = 0.5


def scraper_node(
    state: BettingState,
    *,
    client: BetfairClient | KalshiClient,
    market_id_map: dict[str, list[str]] | None = None,
    event_meta_map: dict[str, dict[str, Any]] | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
    venue: Literal["betfair_exchange", "kalshi"] = "kalshi",
) -> dict[str, Any]:
    """Pull odds from the configured venue and resolve events to fixture_ids.

    Betfair path:
        Uses market_id_map + event_meta_map from a prior listMarketCatalogue
        call in the paper-trader runtime. Resolves via betfair_team_aliases.

    Kalshi path:
        Calls client.get_events() + client.get_market_orderbook() per event.
        Resolves via kalshi_event_aliases (populated by bootstrap_kalshi_aliases.py).
        Raises NotImplementedError until Phase 3 step 5b wires RSA auth.

    Trips the circuit breaker when:
      - Any odds fetch fails.
      - Any response staleness > STALENESS_LIMIT_SEC (Betfair path).
      - More than RESOLUTION_FAILURE_THRESHOLD fraction of events fail to
        resolve (signals the operator needs to run the bootstrap script).

    Args:
        state: current BettingState.
        client: authenticated BetfairClient or KalshiClient.
        market_id_map: Betfair event ID → list of market IDs (Betfair path only).
        event_meta_map: Betfair event ID → {"name", "openDate", "countryCode"}
            (Betfair path only).
        con: warehouse connection. Required for entity resolution.
        venue: which venue path to run.
    """
    if venue == "kalshi":
        return _kalshi_scrape(state, client=client, con=con)
    return _betfair_scrape(
        state,
        client=client,
        market_id_map=market_id_map,
        event_meta_map=event_meta_map,
        con=con,
    )


# ---------------------------------------------------------------------------
# Kalshi scrape path
# ---------------------------------------------------------------------------


def _kalshi_scrape(
    state: BettingState,
    *,
    client: KalshiClient,
    con: duckdb.DuckDBPyConnection | None,
) -> dict[str, Any]:
    """Kalshi scrape path — raises NotImplementedError until step 5b."""
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
            fixture_id = event_ticker  # fallback

        for market in event.get("markets", []):
            snap = _extract_kalshi_snapshot(market, fixture_id, resp.received_at)
            if snap is not None:
                new_snapshots.append(snap)
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
) -> OddsSnapshot | None:
    """Build an OddsSnapshot from a single Kalshi market dict.

    The market dict is expected to carry yes_bid_dollars (float 0.01-0.99)
    and is treated as an OU 2.5 contract: YES = over, NO = under.

    Returns None if required fields are missing or price is out of range.
    """
    from footy_ev.venues.kalshi import price_to_decimal_odds

    yes_bid = market.get("yes_bid_dollars")
    no_bid = market.get("no_bid_dollars")
    if yes_bid is None or no_bid is None:
        return None
    try:
        yes_bid_f = float(yes_bid)
        no_bid_f = float(no_bid)
    except (TypeError, ValueError):
        return None
    if not (0.0 < yes_bid_f < 1.0) or not (0.0 < no_bid_f < 1.0):
        return None

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

    return snapshots[0] if snapshots else None


def _cache_kalshi_resolution_safe(
    con: duckdb.DuckDBPyConnection,
    event_ticker: str,
    res: Any,
) -> None:
    try:
        cache_kalshi_resolution(con, event_ticker, res)
    except Exception:  # noqa: BLE001
        _LOG.debug("scraper: could not cache Kalshi resolution for %s", event_ticker)


# ---------------------------------------------------------------------------
# Betfair scrape path (unchanged from Phase 3 step 3 — kept for compat)
# ---------------------------------------------------------------------------


def _betfair_scrape(
    state: BettingState,
    *,
    client: BetfairClient,
    market_id_map: dict[str, list[str]] | None,
    event_meta_map: dict[str, dict[str, Any]] | None,
    con: duckdb.DuckDBPyConnection | None,
) -> dict[str, Any]:
    fixtures = state.get("fixtures_to_process", [])
    if not fixtures or not market_id_map:
        return {
            "odds_snapshots": [],
            "resolved_fixture_ids": [],
            "data_freshness_seconds": {},
            "circuit_breaker_tripped": False,
        }

    new_snapshots: list[OddsSnapshot] = []
    resolved_fixture_ids: list[str] = []
    freshness: dict[str, int] = {}
    breaker_tripped = False
    breaker_reason = ""
    resolution_attempts = 0
    resolution_failures = 0

    for betfair_event_id in fixtures:
        market_ids = market_id_map.get(betfair_event_id, [])
        if not market_ids:
            continue

        effective_fixture_id = betfair_event_id
        if con is not None and event_meta_map is not None:
            meta = event_meta_map.get(betfair_event_id, {})
            resolution_attempts += 1
            res: EventResolution = resolve_event_from_meta(con, betfair_event_id, meta)
            _cache_betfair_resolution_safe(con, betfair_event_id, res)
            if res.status == "resolved" and res.fixture_id:
                effective_fixture_id = res.fixture_id
                resolved_fixture_ids.append(res.fixture_id)
                _LOG.debug("scraper[betfair]: resolved %s -> %s", betfair_event_id, res.fixture_id)
            else:
                resolution_failures += 1
                _LOG.info(
                    "scraper[betfair]: event %s unresolved (%s): %s",
                    betfair_event_id,
                    res.status,
                    res.reason,
                )
                continue

        try:
            resp = client.list_market_book(market_ids=market_ids)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("betfair listMarketBook failed for %s: %s", betfair_event_id, exc)
            breaker_tripped = True
            breaker_reason = f"listMarketBook failed: {type(exc).__name__}"
            continue

        freshness[f"betfair:{effective_fixture_id}"] = resp.staleness_seconds
        if resp.staleness_seconds > STALENESS_LIMIT_SEC:
            breaker_tripped = True
            breaker_reason = (
                f"betfair odds stale {resp.staleness_seconds}s > {STALENESS_LIMIT_SEC}s"
            )

        new_snapshots.extend(
            _extract_betfair_snapshots(resp.payload, effective_fixture_id, resp.received_at)
        )

    if (
        resolution_attempts > 0
        and resolution_failures / resolution_attempts > _RESOLUTION_FAILURE_THRESHOLD
    ):
        fail_pct = int(100 * resolution_failures / resolution_attempts)
        breaker_tripped = True
        breaker_reason = (
            f"unresolved_event: {resolution_failures}/{resolution_attempts} events "
            f"({fail_pct}%) failed resolution. "
            "Run scripts/bootstrap_betfair_aliases.py to populate betfair_team_aliases."
        )
        _LOG.warning("scraper[betfair]: %s", breaker_reason)

    out: dict[str, Any] = {
        "odds_snapshots": new_snapshots,
        "resolved_fixture_ids": resolved_fixture_ids,
        "data_freshness_seconds": freshness,
        "circuit_breaker_tripped": breaker_tripped,
    }
    if breaker_tripped:
        out["breaker_reason"] = breaker_reason
    return out


def _cache_betfair_resolution_safe(
    con: duckdb.DuckDBPyConnection,
    betfair_event_id: str,
    res: EventResolution,
) -> None:
    try:
        cache_resolution(con, betfair_event_id, res)
    except Exception:  # noqa: BLE001
        _LOG.debug("scraper: could not cache Betfair resolution for %s", betfair_event_id)


def _extract_betfair_snapshots(
    payload: Any, fixture_id: str, captured_at: datetime
) -> list[OddsSnapshot]:
    if not isinstance(payload, list):
        return []
    out: list[OddsSnapshot] = []
    for market in payload:
        if not isinstance(market, dict):
            continue
        market_id: str = market.get("marketId", "")
        runners = market.get("runners", [])
        if len(runners) != 2:
            continue
        for runner in runners:
            sel_id = runner.get("selectionId")
            sel_name = _OU25_SELECTION_BY_ID.get(sel_id)
            if sel_name is None:
                continue
            ex = runner.get("ex", {})
            atb = ex.get("availableToBack", [])
            if not atb:
                continue
            best = atb[0]
            try:
                price = float(best.get("price"))
            except (TypeError, ValueError):
                continue
            liquidity = best.get("size")
            try:
                liquidity_f = float(liquidity) if liquidity is not None else None
            except (TypeError, ValueError):
                liquidity_f = None
            out.append(
                OddsSnapshot(
                    venue="betfair_exchange",
                    fixture_id=fixture_id,
                    market=MarketType.OU_25,
                    selection=sel_name,
                    odds_decimal=price,
                    captured_at=captured_at.astimezone(UTC),
                    staleness_seconds=0,
                    liquidity_gbp=liquidity_f,
                )
            )
        _ = market_id  # kept for future logging
    return out
