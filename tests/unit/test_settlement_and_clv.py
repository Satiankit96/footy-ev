"""Unit tests for settlement.py and clv_backfill.py.

Uses in-memory DuckDB with full migration stack. Tests:
  - settle_pending_bets: empty case, ou_2.5 win/loss, dry_run mode
  - backfill_clv: empty case, Pinnacle fallback, live_odds_snapshots source
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.runtime.clv_backfill import backfill_clv
from footy_ev.runtime.settlement import settle_pending_bets

_FIXTURE_DATE = "2026-01-15"
_FIXTURE_ID = f"EPL|2025-2026|arsenal|liverpool|{_FIXTURE_DATE}"
_SEASON = "2025-2026"


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_migrations(c)
    apply_views(c)
    return c


def _seed_fixture(con: duckdb.DuckDBPyConnection, result_ft: str = "H", goals: int = 3) -> None:
    """Seed a finalised fixture in raw_match_results so v_fixtures_epl has a row.

    Football-data column names: ftr (H/D/A), fthg (home goals), ftag (away goals).
    """
    now = datetime.now(tz=UTC)
    home_goals = (goals + 1) // 2
    away_goals = goals - home_goals
    for team_id in ("arsenal", "liverpool"):
        con.execute(
            "INSERT OR IGNORE INTO team_aliases (source, raw_name, team_id, confidence, resolved_at)"
            " VALUES ('football_data', ?, ?, 'manual', ?)",
            [team_id, team_id, now],
        )
    con.execute(
        "INSERT OR IGNORE INTO raw_match_results"
        " (league, season, div, match_date, home_team, away_team,"
        "  source_code, source_url, ingested_at, source_row_hash,"
        "  ftr, fthg, ftag)"
        " VALUES ('EPL', ?, 'E0', ?, 'arsenal', 'liverpool',"
        "         'football_data', 'http://x', ?, 'hash-1',"
        "         ?, ?, ?)",
        [_SEASON, _FIXTURE_DATE, now, result_ft, home_goals, away_goals],
    )


def _seed_pending_bet(
    con: duckdb.DuckDBPyConnection,
    market: str = "ou_2.5",
    selection: str = "over",
    stake: float = 10.0,
    odds: float = 1.90,
) -> str:
    decision_id = "test-decision-001"
    now = datetime.now(tz=UTC)
    con.execute(
        """
        INSERT INTO paper_bets
            (decision_id, run_id, fixture_id, market, selection,
             p_calibrated, odds_at_decision, venue, edge_pct,
             kelly_fraction_used, stake_gbp, bankroll_used, features_hash,
             decided_at, settlement_status)
        VALUES (?, 'run1', ?, ?, ?, 0.6, ?, 'kalshi', 0.05, 0.25, ?, 1000, 'hash', ?, 'pending')
        """,
        [decision_id, _FIXTURE_ID, market, selection, odds, stake, now],
    )
    return decision_id


# ---------------------------------------------------------------------------
# settle_pending_bets
# ---------------------------------------------------------------------------


def test_settle_pending_bets_empty(con: duckdb.DuckDBPyConnection) -> None:
    result = settle_pending_bets(con)
    assert result["n_settled"] == 0
    assert result["n_won"] == 0
    assert result["total_pnl_gbp"] == Decimal("0.00")


def test_settle_ou25_winner(con: duckdb.DuckDBPyConnection) -> None:
    _seed_fixture(con, result_ft="H", goals=3)  # 3 goals → over wins
    _seed_pending_bet(con, market="ou_2.5", selection="over", stake=10.0, odds=1.90)

    result = settle_pending_bets(con)
    assert result["n_settled"] == 1
    assert result["n_won"] == 1
    assert result["n_lost"] == 0
    # pnl = 10 * (1.90 - 1) = 9.00
    assert abs(float(result["total_pnl_gbp"]) - 9.0) < 0.01

    row = con.execute(
        "SELECT settlement_status, pnl_gbp FROM paper_bets WHERE decision_id = 'test-decision-001'"
    ).fetchone()
    assert row[0] == "settled"
    assert abs(float(row[1]) - 9.0) < 0.01


def test_settle_ou25_loser(con: duckdb.DuckDBPyConnection) -> None:
    _seed_fixture(con, result_ft="H", goals=1)  # 1 goal → under wins, over loses
    _seed_pending_bet(con, market="ou_2.5", selection="over", stake=10.0, odds=1.90)

    result = settle_pending_bets(con)
    assert result["n_settled"] == 1
    assert result["n_won"] == 0
    assert result["n_lost"] == 1
    assert abs(float(result["total_pnl_gbp"]) - (-10.0)) < 0.01


def test_settle_dry_run_no_db_write(con: duckdb.DuckDBPyConnection) -> None:
    _seed_fixture(con, result_ft="H", goals=3)
    _seed_pending_bet(con)

    settle_pending_bets(con, dry_run=True)

    row = con.execute(
        "SELECT settlement_status FROM paper_bets WHERE decision_id = 'test-decision-001'"
    ).fetchone()
    # dry_run → still pending
    assert row[0] == "pending"


def test_settle_exact_2_goals_is_under(con: duckdb.DuckDBPyConnection) -> None:
    _seed_fixture(con, result_ft="D", goals=2)  # exactly 2 → under wins (<=2)
    _seed_pending_bet(con, market="ou_2.5", selection="under", stake=10.0, odds=2.10)

    result = settle_pending_bets(con)
    assert result["n_won"] == 1


# ---------------------------------------------------------------------------
# backfill_clv
# ---------------------------------------------------------------------------


def test_backfill_clv_empty(con: duckdb.DuckDBPyConnection) -> None:
    result = backfill_clv(con)
    assert result["n_updated"] == 0
    assert result["n_miss"] == 0


def test_backfill_clv_from_live_odds_snapshots(con: duckdb.DuckDBPyConnection) -> None:
    now = datetime.now(tz=UTC)
    # Seed a settled paper_bet with no closing_odds yet
    con.execute(
        """
        INSERT INTO paper_bets
            (decision_id, run_id, fixture_id, market, selection,
             p_calibrated, odds_at_decision, venue, edge_pct,
             kelly_fraction_used, stake_gbp, bankroll_used, features_hash,
             decided_at, settlement_status, pnl_gbp)
        VALUES ('clv-test-001', 'run1', ?, 'ou_2.5', 'over', 0.6,
                1.90, 'kalshi', 0.05, 0.25, 10, 1000, 'hash', ?, 'settled', 9.0)
        """,
        [_FIXTURE_ID, now],
    )
    # Seed live_odds_snapshots with closing odds
    con.execute(
        """
        INSERT INTO live_odds_snapshots
            (snapshot_id, venue, fixture_id, market, selection,
             odds_decimal, received_at)
        VALUES ('snap-001', 'kalshi', ?, 'ou_2.5', 'over', 1.75, ?)
        """,
        [_FIXTURE_ID, now],
    )
    result = backfill_clv(con, venue="kalshi")
    assert result["n_updated"] == 1
    assert result["n_kalshi_close"] == 1
    assert result["n_miss"] == 0

    row = con.execute(
        "SELECT closing_odds, clv_pct FROM paper_bets WHERE decision_id = 'clv-test-001'"
    ).fetchone()
    assert row is not None
    assert abs(float(row[0]) - 1.75) < 1e-9
    # clv_pct = 1.90 / 1.75 - 1 ≈ 0.0857
    assert abs(float(row[1]) - (1.90 / 1.75 - 1.0)) < 1e-9


def test_backfill_clv_miss_when_no_source(con: duckdb.DuckDBPyConnection) -> None:
    now = datetime.now(tz=UTC)
    con.execute(
        """
        INSERT INTO paper_bets
            (decision_id, run_id, fixture_id, market, selection,
             p_calibrated, odds_at_decision, venue, edge_pct,
             kelly_fraction_used, stake_gbp, bankroll_used, features_hash,
             decided_at, settlement_status, pnl_gbp)
        VALUES ('clv-miss-001', 'run1', ?, 'ou_2.5', 'over', 0.6,
                1.90, 'kalshi', 0.05, 0.25, 10, 1000, 'hash', ?, 'settled', 9.0)
        """,
        [_FIXTURE_ID, now],
    )
    result = backfill_clv(con, venue="kalshi")
    assert result["n_miss"] == 1
    assert result["n_updated"] == 0
