"""Unit tests for orchestration.nodes.execution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import duckdb
import pytest

from footy_ev.db import apply_migrations
from footy_ev.orchestration.nodes.execution import execution_node
from footy_ev.orchestration.state import BetDecision, MarketType


@pytest.fixture
def warehouse() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    return con


def _approved() -> BetDecision:
    return BetDecision(
        fixture_id="ARS-LIV",
        market=MarketType.OU_25,
        selection="over",
        odds_at_decision=2.05,
        p_calibrated=0.55,
        sigma_p=0.0,
        edge_pct=0.05,
        kelly_fraction_used=0.005,
        stake_gbp=Decimal("5.00"),
        bankroll_used=Decimal("1000.00"),
        venue="betfair_exchange",
        decided_at=datetime(2026, 5, 6, 22, 0, 0, tzinfo=UTC),
        features_hash="abc123",
        run_id=None,
    )


def test_execution_writes_paper_bet(warehouse: duckdb.DuckDBPyConnection) -> None:
    execution_node({"placed_bets": [_approved()]}, con=warehouse)
    rows = warehouse.execute("SELECT COUNT(*) FROM paper_bets").fetchone()
    assert rows[0] == 1


def test_execution_idempotent(warehouse: duckdb.DuckDBPyConnection) -> None:
    bet = _approved()
    execution_node({"placed_bets": [bet]}, con=warehouse)
    execution_node({"placed_bets": [bet]}, con=warehouse)
    rows = warehouse.execute("SELECT COUNT(*) FROM paper_bets").fetchone()
    assert rows[0] == 1  # ON CONFLICT DO NOTHING


def test_execution_no_op_without_bets(warehouse: duckdb.DuckDBPyConnection) -> None:
    out = execution_node({"placed_bets": []}, con=warehouse)
    rows = warehouse.execute("SELECT COUNT(*) FROM paper_bets").fetchone()
    assert rows[0] == 0
    assert out == {}


def test_execution_paper_only_under_live_trading_flag(
    warehouse: duckdb.DuckDBPyConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with LIVE_TRADING=true, step 1 has no real-execution path:
    bets land in paper_bets and a warning is logged."""
    monkeypatch.setenv("LIVE_TRADING", "true")
    execution_node({"placed_bets": [_approved()]}, con=warehouse)
    rows = warehouse.execute("SELECT COUNT(*) FROM paper_bets").fetchone()
    assert rows[0] == 1
    monkeypatch.delenv("LIVE_TRADING", raising=False)
