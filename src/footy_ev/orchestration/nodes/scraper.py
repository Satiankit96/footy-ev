"""Scraper node — pulls odds from Betfair, resolves events to fixture_ids."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import duckdb

from footy_ev.orchestration.state import BettingState, MarketType, OddsSnapshot
from footy_ev.venues import BetfairClient
from footy_ev.venues.resolution import (
    EventResolution,
    cache_resolution,
    resolve_event_from_meta,
)

_LOG = logging.getLogger(__name__)
STALENESS_LIMIT_SEC = 300

# Betfair Selection ID lookup is market-specific; Phase 3 step 1 only handles
# OU 2.5 (selectionId 1 = Over, 2 = Under by Betfair convention) and 1X2
# (Home/Draw/Away by runner.runnerName).
_OU25_SELECTION_BY_ID: dict[int, str] = {1: "over", 2: "under"}

# If this fraction of events fail to resolve, the circuit breaker trips.
_RESOLUTION_FAILURE_THRESHOLD = 0.5


def scraper_node(
    state: BettingState,
    *,
    client: BetfairClient,
    market_id_map: dict[str, list[str]] | None = None,
    event_meta_map: dict[str, dict[str, Any]] | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Pull Betfair listMarketBook for fixtures-to-process.

    If `con` and `event_meta_map` are provided, resolves each Betfair event
    ID to a warehouse fixture_id via betfair_team_aliases and emits
    `resolved_fixture_ids` in the output state. OddsSnapshots use the
    warehouse fixture_id when resolved, the Betfair event ID otherwise.

    Trips the circuit breaker when:
      - Any listMarketBook call fails.
      - Any response staleness > STALENESS_LIMIT_SEC.
      - More than RESOLUTION_FAILURE_THRESHOLD fraction of events fail to
        resolve (signals the operator needs to run bootstrap_betfair_aliases).

    Args:
        state: current BettingState.
        client: authenticated BetfairClient.
        market_id_map: Betfair event ID → list of market IDs. Populated by
            the paper-trader runtime from a prior listMarketCatalogue call.
        event_meta_map: Betfair event ID → {"name", "openDate", "countryCode"}
            from listEvents. Used for entity resolution.
        con: warehouse connection. Required for entity resolution.
    """
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

        # --- Entity resolution ---
        effective_fixture_id = betfair_event_id  # fallback: Betfair ID
        if con is not None and event_meta_map is not None:
            meta = event_meta_map.get(betfair_event_id, {})
            resolution_attempts += 1
            res: EventResolution = resolve_event_from_meta(con, betfair_event_id, meta)
            _cache_resolution_safe(con, betfair_event_id, res)
            if res.status == "resolved" and res.fixture_id:
                effective_fixture_id = res.fixture_id
                resolved_fixture_ids.append(res.fixture_id)
                _LOG.debug(
                    "scraper: resolved betfair_event_id=%s → fixture_id=%s",
                    betfair_event_id,
                    res.fixture_id,
                )
            else:
                resolution_failures += 1
                _LOG.info(
                    "scraper: event %s unresolved (%s): %s",
                    betfair_event_id,
                    res.status,
                    res.reason,
                )
                # Drop this event — no warehouse fixture_id, no bet possible
                continue

        # --- Odds fetch ---
        try:
            resp = client.list_market_book(market_ids=market_ids)
        except Exception as exc:  # noqa: BLE001 — surface upstream error
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
            _extract_snapshots(resp.payload, effective_fixture_id, resp.received_at)
        )

    # Trip breaker if too many resolution failures
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
        _LOG.warning("scraper: %s", breaker_reason)

    out: dict[str, Any] = {
        "odds_snapshots": new_snapshots,
        "resolved_fixture_ids": resolved_fixture_ids,
        "data_freshness_seconds": freshness,
        "circuit_breaker_tripped": breaker_tripped,
    }
    if breaker_tripped:
        out["breaker_reason"] = breaker_reason
    return out


def _cache_resolution_safe(
    con: duckdb.DuckDBPyConnection,
    betfair_event_id: str,
    res: EventResolution,
) -> None:
    """Write to betfair_event_resolutions; silently ignore errors."""
    try:
        cache_resolution(con, betfair_event_id, res)
    except Exception:  # noqa: BLE001
        _LOG.debug("scraper: could not cache resolution for %s", betfair_event_id)


def _extract_snapshots(payload: Any, fixture_id: str, captured_at: datetime) -> list[OddsSnapshot]:
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
