"""Paper-trading runtime — Kalshi venue (US-legal, NY operator).

This module is the only place that knows how to talk to all three external
systems at once (Kalshi API, the warehouse, the SQLite checkpoint store).
Every other module stays narrow and testable.
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
from footy_ev.venues.kalshi import KalshiClient, _KalshiCredentialError

_LOG = logging.getLogger(__name__)
DEFAULT_DB_PATH = Path("data/warehouse/footy_ev.duckdb")
DEFAULT_TICK_SECONDS = 300
DEFAULT_BANKROLL = 1000.0
DEFAULT_EDGE_THRESHOLD = 0.03
DEFAULT_FIXTURES_AHEAD_DAYS = 7
_MODEL_RUN_ID_ENV = "PAPER_TRADER_MODEL_RUN_ID"
COMMISSION_PCT = 0.07  # Kalshi placeholder; replace with live rate once confirmed


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


def _build_client_from_env() -> KalshiClient:
    """Construct KalshiClient from environment variables.

    Reads KALSHI_API_KEY_ID and data/kalshi_private_key.pem (default path,
    overridden by KALSHI_PEM_PATH).

    Raises:
        RuntimeError: if credentials are missing or the PEM is unreadable.
    """
    try:
        return KalshiClient.from_env()
    except _KalshiCredentialError as exc:
        raise RuntimeError(str(exc)) from exc


def run_once(
    cfg: PaperTraderConfig,
    *,
    client: KalshiClient | None = None,
    score_fn: Callable[..., list[dict[str, Any]]] | None = None,
    warehouse_con: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Single-pass: run the graph once, persist summary.

    Fixture discovery happens inside the scraper node via
    KalshiClient.get_events(). Until Phase 3 step 5b parsers are wired,
    this trips the circuit breaker immediately with a clear
    NotImplementedError message — that is the intended fail-fast behavior.

    Returns a small dict suitable for `run.py paper-trade --once` output.
    """
    started_at = datetime.now(tz=UTC)
    venue_client = client or _build_client_from_env()
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

    # Kalshi: scraper discovers events internally via get_events().
    fixture_ids: list[str] = []
    invocation_id = make_invocation_id(fixture_ids, started_at)

    g = build_graph(
        kalshi=venue_client,
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
            affected_source="kalshi",
            tripped_at=completed_at,
        )

    return {
        "invocation_id": invocation_id,
        "n_fixtures": len(fixture_ids),
        "n_candidates": len(candidates),
        "n_approved": len(approved),
        "breaker_tripped": breaker_tripped,
        "last_error": last_error,
        "venue": "kalshi",
    }


def run_forever(cfg: PaperTraderConfig) -> None:
    """Blocking loop. Ctrl-C to stop. Re-uses venue client session across ticks."""
    venue_client = _build_client_from_env()
    while True:
        try:
            summary = run_once(cfg, client=venue_client)
            _LOG.info(
                "paper-trade tick: venue=kalshi invocation=%s fixtures=%d "
                "candidates=%d approved=%d breaker=%s",
                summary["invocation_id"],
                summary["n_fixtures"],
                summary["n_candidates"],
                summary["n_approved"],
                summary["breaker_tripped"],
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("paper-trade tick failed: %s", exc)
        time.sleep(cfg.tick_seconds)
