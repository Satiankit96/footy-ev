"""Paper-trading runtime.

Polls Betfair Exchange for upcoming EPL fixtures (next N days), invokes
the LangGraph for each fixture every 5 minutes, persists every state
transition. Designed to run continuously via `python run.py paper-trade`
or a cron job.

This module is the only place that knows how to talk to all three
external systems at once (Betfair API, the warehouse, the SQLite
checkpoint store). Every other module stays narrow and testable.
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from footy_ev.db import apply_migrations, apply_views
from footy_ev.orchestration.checkpoints import (
    log_circuit_breaker,
    make_invocation_id,
    write_summary,
)
from footy_ev.orchestration.graph import (
    DEFAULT_CHECKPOINT_PATH,
    build_graph,
    compile_graph,
)
from footy_ev.orchestration.state import BettingState
from footy_ev.venues import BetfairClient

_LOG = logging.getLogger(__name__)
DEFAULT_DB_PATH = Path("data/warehouse/footy_ev.duckdb")
DEFAULT_TICK_SECONDS = 300
DEFAULT_BANKROLL = 1000.0
DEFAULT_EDGE_THRESHOLD = 0.03
DEFAULT_FIXTURES_AHEAD_DAYS = 7
EPL_COUNTRY_CODE = "GB"
_MODEL_RUN_ID_ENV = "PAPER_TRADER_MODEL_RUN_ID"


@dataclass
class PaperTraderConfig:
    fixtures_ahead_days: int = DEFAULT_FIXTURES_AHEAD_DAYS
    bankroll_gbp: float = DEFAULT_BANKROLL
    edge_threshold_pct: float = DEFAULT_EDGE_THRESHOLD
    tick_seconds: int = DEFAULT_TICK_SECONDS
    db_path: Path = field(default_factory=lambda: DEFAULT_DB_PATH)
    checkpoint_path: Path = field(default_factory=lambda: DEFAULT_CHECKPOINT_PATH)
    model_run_id: str | None = None


def _open_warehouse(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    apply_views(con)
    return con


def _build_betfair_from_env() -> BetfairClient:
    app_key = os.environ.get("BETFAIR_APP_KEY")
    username = os.environ.get("BETFAIR_USERNAME")
    password = os.environ.get("BETFAIR_PASSWORD")
    missing = [
        name
        for name, value in [
            ("BETFAIR_APP_KEY", app_key),
            ("BETFAIR_USERNAME", username),
            ("BETFAIR_PASSWORD", password),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"missing required env vars for paper trader: {', '.join(missing)}. "
            "See docs/SETUP_GUIDE.md."
        )
    assert app_key is not None and username is not None and password is not None
    return BetfairClient(app_key=app_key, username=username, password=password)


def _resolve_fixtures_and_markets(
    betfair: BetfairClient, days_ahead: int
) -> tuple[list[str], dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Returns (betfair_event_ids, market_id_map, event_meta_map).

    `betfair_event_ids` are the Betfair event IDs for events that have
    at least one OU 2.5 market. `event_meta_map` carries the raw event
    metadata (name, openDate, countryCode) keyed by event ID so the
    scraper node can resolve them to warehouse fixture_ids at run time.
    """
    events_resp = betfair.list_events(country_codes=[EPL_COUNTRY_CODE], days_ahead=days_ahead)
    event_ids: list[str] = []
    event_meta: dict[str, dict[str, Any]] = {}
    if isinstance(events_resp.payload, list):
        for entry in events_resp.payload:
            ev = entry.get("event") if isinstance(entry, dict) else None
            if not ev:
                continue
            eid = ev.get("id")
            if eid:
                eid_str = str(eid)
                event_ids.append(eid_str)
                event_meta[eid_str] = {
                    "name": ev.get("name", ""),
                    "openDate": ev.get("openDate", ""),
                    "countryCode": ev.get("countryCode", ""),
                }
    if not event_ids:
        return [], {}, {}

    cat_resp = betfair.list_market_catalogue(event_ids=event_ids, market_types=["OVER_UNDER_25"])
    market_map: dict[str, list[str]] = {}
    if isinstance(cat_resp.payload, list):
        for market in cat_resp.payload:
            if not isinstance(market, dict):
                continue
            ev = market.get("event") or {}
            event_id = str(ev.get("id", ""))
            market_id = market.get("marketId")
            if event_id and market_id:
                market_map.setdefault(event_id, []).append(str(market_id))

    fixture_ids = list(market_map.keys())
    return fixture_ids, market_map, event_meta


def run_once(
    cfg: PaperTraderConfig,
    *,
    betfair: BetfairClient | None = None,
    score_fn: Callable[..., list[dict[str, Any]]] | None = None,
    warehouse_con: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Single-pass: resolve fixtures, run the graph, persist summary.

    Returns a small dict suitable for `run.py paper-trade --once` output.
    """
    started_at = datetime.now(tz=UTC)
    bf = betfair or _build_betfair_from_env()
    con = warehouse_con or _open_warehouse(cfg.db_path)

    effective_score_fn = score_fn
    if effective_score_fn is None:
        from footy_ev.runtime.model_loader import (
            NoProductionModelError,
            detect_production_run_id,
            load_production_scorer,
        )

        run_id = (
            cfg.model_run_id or os.environ.get(_MODEL_RUN_ID_ENV) or detect_production_run_id(con)
        )
        try:
            effective_score_fn = load_production_scorer(con, run_id)
            _LOG.info("paper-trade: using production scorer for run_id=%s", run_id)
        except NoProductionModelError:
            _LOG.warning(
                "paper-trade: no production model found; analyst will emit zero probabilities. "
                "Run `python run.py canonical` to generate a qualifying XGBoost backtest."
            )

    fixture_ids, market_map, event_meta = _resolve_fixtures_and_markets(bf, cfg.fixtures_ahead_days)
    invocation_id = make_invocation_id(fixture_ids, started_at)

    g = build_graph(
        betfair=bf,
        market_id_map=market_map,
        event_meta_map=event_meta,
        score_fn=effective_score_fn,
        warehouse_con=con,
    )
    compiled, sqlite_conn = compile_graph(g, checkpoint_path=cfg.checkpoint_path)

    initial: BettingState = {
        "fixtures_to_process": fixture_ids,
        "as_of": started_at,
        "bankroll_gbp": cfg.bankroll_gbp,
        "edge_threshold_pct": cfg.edge_threshold_pct,
        "invocation_id": invocation_id,
    }
    final_state: dict[str, Any] = {}
    last_error: str | None = None
    try:
        final_state = compiled.invoke(
            initial,
            config={"configurable": {"thread_id": invocation_id}},
        )
    except Exception as exc:  # noqa: BLE001 — runtime error surfacing
        last_error = f"{type(exc).__name__}: {exc}"
        _LOG.exception("paper-trade invocation failed: %s", last_error)
    finally:
        with contextlib.suppress(Exception):
            sqlite_conn.close()

    completed_at = datetime.now(tz=UTC)
    candidates = final_state.get("candidate_bets", []) or []
    approved = final_state.get("placed_bets", []) or []
    breaker_tripped = bool(final_state.get("circuit_breaker_tripped", False))
    breaker_reason = final_state.get("breaker_reason")

    write_summary(
        con,
        invocation_id=invocation_id,
        fixture_ids=fixture_ids,
        started_at=started_at,
        completed_at=completed_at,
        final_node="execution" if not breaker_tripped else "circuit_breaker",
        n_candidate_bets=len(candidates),
        n_approved_bets=len(approved),
        breaker_tripped=breaker_tripped,
        breaker_reason=breaker_reason,
        last_error=last_error,
        sqlite_thread_id=invocation_id,
    )
    if breaker_tripped:
        log_circuit_breaker(
            con,
            reason=breaker_reason or "unknown",
            affected_source="betfair_exchange",
            tripped_at=completed_at,
        )

    return {
        "invocation_id": invocation_id,
        "n_fixtures": len(fixture_ids),
        "n_candidates": len(candidates),
        "n_approved": len(approved),
        "breaker_tripped": breaker_tripped,
        "last_error": last_error,
    }


def run_forever(cfg: PaperTraderConfig) -> None:
    """Blocking loop. Ctrl-C to stop. Re-uses Betfair session across ticks."""
    bf = _build_betfair_from_env()
    while True:
        try:
            summary = run_once(cfg, betfair=bf)
            _LOG.info(
                "paper-trade tick: invocation=%s fixtures=%d candidates=%d approved=%d breaker=%s",
                summary["invocation_id"],
                summary["n_fixtures"],
                summary["n_candidates"],
                summary["n_approved"],
                summary["breaker_tripped"],
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("paper-trade tick failed: %s", exc)
        time.sleep(cfg.tick_seconds)
