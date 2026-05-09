"""Sanity checks for the migration runner and migration 001 SQL."""

from __future__ import annotations

import duckdb

from footy_ev.db import apply_migrations


def test_apply_migrations_creates_expected_tables() -> None:
    con = duckdb.connect(":memory:")
    applied = apply_migrations(con)

    assert applied == [
        "001_raw_match_results.sql",
        "002_promote_closing_odds.sql",
        "003_raw_understat_matches.sql",
        "004_phase1_model_artifacts.sql",
        "005_clv_calibration_artifacts.sql",
        "006_eval_market_column_xg_artifacts.sql",
        "007_xgb_artifacts.sql",
        "008_bet_sizing_decisions.sql",
        "009_paper_trading.sql",
    ]

    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert {
        "raw_match_results",
        "teams",
        "schema_drift_log",
        "raw_understat_matches",
        "team_aliases",
        "model_predictions",
        "dc_fits",
        "dc_team_params",
        "backtest_runs",
        "clv_evaluations",
        "calibration_fits",
        "reliability_bins",
        "xg_fits",
        "xg_team_params",
        "xgb_fits",
        "xgb_feature_importances",
        "bet_sizing_decisions",
        "paper_bets",
        "live_odds_snapshots",
        "langgraph_checkpoint_summaries",
        "circuit_breaker_log",
    }.issubset(tables)

    # Migration 006: market column present in CLV / calibration / reliability tables.
    cols_clv = {r[0] for r in con.execute("DESCRIBE clv_evaluations").fetchall()}
    cols_cal = {r[0] for r in con.execute("DESCRIBE calibration_fits").fetchall()}
    cols_rel = {r[0] for r in con.execute("DESCRIBE reliability_bins").fetchall()}
    assert "market" in cols_clv
    assert "market" in cols_cal
    assert "market" in cols_rel


def test_migration_003_raw_understat_matches_pk_enforced() -> None:
    """raw_understat_matches PK on understat_match_id rejects duplicates."""
    con = duckdb.connect(":memory:")
    apply_migrations(con)

    insert_sql = """
        INSERT INTO raw_understat_matches (
            league, season, source_code, source_url, ingested_at, source_row_hash,
            understat_match_id, understat_home_id, understat_away_id,
            home_team_raw, away_team_raw,
            kickoff_local, kickoff_utc, is_result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    row = (
        "EPL",
        "2024-2025",
        "understat",
        "https://understat.com/league/EPL/2024",
        "2026-04-26 00:00:00",
        "h1",
        "14048",
        "89",
        "82",
        "Manchester United",
        "Fulham",
        "2024-08-16 20:00:00",
        "2024-08-16 19:00:00",
        True,
    )
    con.execute(insert_sql, row)

    try:
        con.execute(insert_sql, row)
    except duckdb.ConstraintException:
        return
    raise AssertionError("expected ConstraintException on duplicate understat_match_id PK")


def test_raw_match_results_primary_key_enforced() -> None:
    con = duckdb.connect(":memory:")
    apply_migrations(con)

    insert_sql = """
        INSERT INTO raw_match_results (
            league, season, source_code, source_url, ingested_at, source_row_hash,
            div, match_date, home_team, away_team
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    row = (
        "EPL",
        "2024-2025",
        "E0",
        "https://example/E0.csv",
        "2026-04-24 00:00:00",
        "h1",
        "E0",
        "2024-08-16",
        "Man United",
        "Fulham",
    )
    con.execute(insert_sql, row)

    try:
        con.execute(insert_sql, row)
    except duckdb.ConstraintException:
        return
    raise AssertionError("expected ConstraintException on duplicate PK, got none")


def test_apply_migrations_is_idempotent() -> None:
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    apply_migrations(con)  # second pass must not raise
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert "raw_match_results" in tables
