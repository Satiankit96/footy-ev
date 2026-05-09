"""Scraper node — pulls odds from Betfair and enforces staleness limit."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from footy_ev.orchestration.state import BettingState, MarketType, OddsSnapshot
from footy_ev.venues import BetfairClient

_LOG = logging.getLogger(__name__)
STALENESS_LIMIT_SEC = 300

# Betfair Selection ID lookup is market-specific; Phase 3 step 1 only handles
# OU 2.5 (selectionId 1 = Over, 2 = Under by Betfair convention) and 1X2
# (Home/Draw/Away by runner.runnerName).
_OU25_SELECTION_BY_ID: dict[int, str] = {1: "over", 2: "under"}


def scraper_node(
    state: BettingState,
    *,
    client: BetfairClient,
    market_id_map: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Pulls Betfair listMarketBook for fixtures-to-process.

    `market_id_map` is fixture_id -> [betfair_market_id], typically
    populated by a prior listMarketCatalogue call (managed by the
    paper-trader runtime). When absent we return early — the graph
    cannot scrape what it cannot resolve.
    """
    fixtures = state.get("fixtures_to_process", [])
    if not fixtures or not market_id_map:
        return {
            "odds_snapshots": [],
            "data_freshness_seconds": {},
            "circuit_breaker_tripped": False,
        }

    new_snapshots: list[OddsSnapshot] = []
    freshness: dict[str, int] = {}
    breaker_tripped = False
    breaker_reason = ""

    for fixture_id in fixtures:
        market_ids = market_id_map.get(fixture_id, [])
        if not market_ids:
            continue
        try:
            resp = client.list_market_book(market_ids=market_ids)
        except Exception as exc:  # noqa: BLE001 — surface upstream error
            _LOG.warning("betfair listMarketBook failed for %s: %s", fixture_id, exc)
            breaker_tripped = True
            breaker_reason = f"listMarketBook failed: {type(exc).__name__}"
            continue

        freshness[f"betfair:{fixture_id}"] = resp.staleness_seconds
        if resp.staleness_seconds > STALENESS_LIMIT_SEC:
            breaker_tripped = True
            breaker_reason = (
                f"betfair odds stale {resp.staleness_seconds}s > {STALENESS_LIMIT_SEC}s"
            )

        new_snapshots.extend(_extract_snapshots(resp.payload, fixture_id, resp.received_at))

    out: dict[str, Any] = {
        "odds_snapshots": new_snapshots,
        "data_freshness_seconds": freshness,
        "circuit_breaker_tripped": breaker_tripped,
    }
    if breaker_tripped:
        out["breaker_reason"] = breaker_reason
    return out


def _extract_snapshots(payload: Any, fixture_id: str, captured_at: datetime) -> list[OddsSnapshot]:
    if not isinstance(payload, list):
        return []
    out: list[OddsSnapshot] = []
    for market in payload:
        if not isinstance(market, dict):
            continue
        market_id: str = market.get("marketId", "")
        # We only encode OU 2.5 in this step. Heuristic: Betfair OU25 markets
        # have exactly two runners with selectionId in {1, 2}.
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
        # one market per fixture per call in this step
        _ = market_id  # kept for future logging
    return out
