"""Sanity checks for the migration runner and migration 001 SQL."""

from __future__ import annotations

import duckdb

from footy_ev.db import apply_migrations


def test_apply_migrations_creates_expected_tables() -> None:
    con = duckdb.connect(":memory:")
    applied = apply_migrations(con)

    assert applied == ["001_raw_match_results.sql", "002_promote_closing_odds.sql"]

    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert {"raw_match_results", "teams", "schema_drift_log"}.issubset(tables)


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
