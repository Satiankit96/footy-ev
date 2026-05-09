"""End-to-end integration test for the LangGraph paper-trading pipeline.

Drives the full graph against:
  - a real on-disk DuckDB warehouse (with migrations applied)
  - a real SQLite checkpoint file
  - a mocked BetfairClient (no network)
  - a fake score function that produces a single edge candidate

Asserts the full happy path: scraper -> news -> analyst -> pricing ->
risk -> execution writes one paper_bet, one summary row, and zero
breaker events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.runtime import PaperTraderConfig, run_once
from footy_ev.venues.betfair import BetfairResponse


@pytest.fixture
def warehouse_path(tmp_path: Path) -> Path:
    return tmp_path / "warehouse.duckdb"


@pytest.fixture
def warehouse(warehouse_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(warehouse_path))
    apply_migrations(con)
    apply_views(con)
    return con


def _bf_mock() -> MagicMock:
    bf = MagicMock()
    now = datetime.now(tz=UTC)
    bf.list_events.return_value = BetfairResponse(
        payload=[{"event": {"id": "31415", "name": "ARS v LIV"}}], received_at=now
    )
    bf.list_market_catalogue.return_value = BetfairResponse(
        payload=[
            {
                "marketId": "1.31415.OU25",
                "marketName": "Over/Under 2.5 Goals",
                "event": {"id": "31415"},
            }
        ],
        received_at=now,
    )
    bf.list_market_book.return_value = BetfairResponse(
        payload=[
            {
                "marketId": "1.31415.OU25",
                "lastMatchTime": now.isoformat(),
                "runners": [
                    {"selectionId": 1, "ex": {"availableToBack": [{"price": 2.10, "size": 500.0}]}},
                    {"selectionId": 2, "ex": {"availableToBack": [{"price": 1.80, "size": 500.0}]}},
                ],
            }
        ],
        received_at=now,
        source_timestamp=now,
        staleness_seconds=15,
    )
    return bf


def _score_fn(_fixtures: list[str], _as_of: Any) -> list[dict[str, Any]]:
    return [
        {
            "fixture_id": "31415",
            "market": "ou_2.5",
            "selection": "over",
            "p_calibrated": 0.55,
            "p_raw": 0.55,
            "sigma_p": 0.0,
            "model_version": "xgb_ou25_v1",
        }
    ]


def test_orchestration_e2e_happy_path(
    warehouse: duckdb.DuckDBPyConnection,
    warehouse_path: Path,
    tmp_path: Path,
) -> None:
    cfg = PaperTraderConfig(
        fixtures_ahead_days=7,
        bankroll_gbp=1000.0,
        edge_threshold_pct=0.03,
        db_path=warehouse_path,
        checkpoint_path=tmp_path / "checkpoints.sqlite",
    )
    out = run_once(cfg, betfair=_bf_mock(), score_fn=_score_fn, warehouse_con=warehouse)
    assert out["n_fixtures"] == 1
    assert out["n_approved"] == 1
    assert not out["breaker_tripped"]

    # Persistence side-effects
    n_bets = warehouse.execute("SELECT COUNT(*) FROM paper_bets").fetchone()[0]
    assert n_bets == 1
    n_summaries = warehouse.execute(
        "SELECT COUNT(*) FROM langgraph_checkpoint_summaries"
    ).fetchone()[0]
    assert n_summaries == 1
    n_breaker = warehouse.execute("SELECT COUNT(*) FROM circuit_breaker_log").fetchone()[0]
    assert n_breaker == 0

    # The checkpoint file was created (sqlite blob, not analytical)
    checkpoint_file = tmp_path / "checkpoints.sqlite"
    assert checkpoint_file.exists()

    # Bet integrity: edge ~5%, stake non-zero Decimal
    row = warehouse.execute(
        "SELECT edge_pct, stake_gbp, p_calibrated, odds_at_decision FROM paper_bets LIMIT 1"
    ).fetchone()
    assert row[0] > 0.03  # edge above threshold
    assert float(row[1]) > 0.0  # stake non-zero
    assert row[2] == pytest.approx(0.55)
    assert row[3] == pytest.approx(2.10)
