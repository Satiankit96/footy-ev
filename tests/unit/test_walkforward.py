"""Unit tests for walk_forward_splits.

Uses an in-memory DuckDB with a synthetic table named `v_fixtures_epl`
(the parametrized default `fixtures_view` name) — splits queries are
shape-only and don't require the real view's full column set.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from footy_ev.backtest.walkforward import _MODEL_REGISTRY, walk_forward_splits


def _create_synthetic_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE v_fixtures_epl (
            league VARCHAR,
            season VARCHAR,
            kickoff_utc TIMESTAMP,
            status VARCHAR
        )
        """
    )


def _seed_4_seasons(con: duckdb.DuckDBPyConnection) -> None:
    """4 seasons, 4 final matches per season, monotonic dates."""
    rows = []
    seasons = ["2020-2021", "2021-2022", "2022-2023", "2023-2024"]
    for s_idx, season in enumerate(seasons):
        for m in range(4):
            rows.append(
                (
                    "EPL",
                    season,
                    datetime(2020 + s_idx, 8 + m, 15),
                    "final",
                )
            )
    con.executemany(
        "INSERT INTO v_fixtures_epl VALUES (?, ?, ?, ?)",
        rows,
    )


def test_walk_forward_splits_basic_shape():
    con = duckdb.connect(":memory:")
    _create_synthetic_table(con)
    _seed_4_seasons(con)
    splits = list(walk_forward_splits(con, "EPL", train_min_seasons=3, step_days=30))
    assert len(splits) > 0
    # Strict half-open: prev test_end == next train_cutoff
    for s_prev, s_next in zip(splits, splits[1:], strict=False):
        assert s_prev[2] == s_next[0]
    # train_cutoff == test_start
    for cutoff, start, end in splits:
        assert cutoff == start
        assert end > start


def test_walk_forward_splits_too_few_seasons():
    con = duckdb.connect(":memory:")
    _create_synthetic_table(con)
    con.execute("INSERT INTO v_fixtures_epl VALUES ('EPL', '2020-2021', '2020-08-15', 'final')")
    splits = list(walk_forward_splits(con, "EPL", train_min_seasons=3, step_days=7))
    assert splits == []


def test_walk_forward_splits_starts_strictly_after_warmup_end():
    """First train_cutoff must be > max(kickoff_utc) of warmup_end_season."""
    con = duckdb.connect(":memory:")
    _create_synthetic_table(con)
    _seed_4_seasons(con)
    warmup_end = con.execute(
        "SELECT MAX(kickoff_utc) FROM v_fixtures_epl "
        "WHERE league = 'EPL' AND season = '2022-2023' AND status = 'final'"
    ).fetchone()[0]
    splits = list(walk_forward_splits(con, "EPL", train_min_seasons=3, step_days=30))
    assert splits[0][0] > warmup_end


def test_walk_forward_splits_ignores_non_final():
    """Scheduled (non-final) matches in warmup season do not push warmup end forward."""
    con = duckdb.connect(":memory:")
    _create_synthetic_table(con)
    _seed_4_seasons(con)
    # Add a far-future scheduled match in warmup season; should be ignored.
    con.execute("INSERT INTO v_fixtures_epl VALUES ('EPL', '2022-2023', '2099-12-31', 'scheduled')")
    splits = list(walk_forward_splits(con, "EPL", train_min_seasons=3, step_days=30))
    # Without the scheduled-row filter, splits would start in year 2099 and
    # be empty (final_ts < cutoff). With the filter, splits exist.
    assert len(splits) > 0


def test_walk_forward_splits_unknown_league_yields_nothing():
    con = duckdb.connect(":memory:")
    _create_synthetic_table(con)
    _seed_4_seasons(con)
    splits = list(walk_forward_splits(con, "LL", train_min_seasons=3, step_days=7))
    assert splits == []


# -------------------------------------------------------------------------
# Model dispatch registry
# -------------------------------------------------------------------------


def test_registry_dc_v1_market_is_1x2():
    assert "dc_v1" in _MODEL_REGISTRY
    assert _MODEL_REGISTRY["dc_v1"]["market"] == "1x2"


def test_registry_xg_skellam_v1_market_is_ou25():
    assert "xg_skellam_v1" in _MODEL_REGISTRY
    assert _MODEL_REGISTRY["xg_skellam_v1"]["market"] == "ou_2.5"


def test_unknown_model_version_raises():
    """run_backtest raises ValueError immediately for an unrecognised model_version."""
    from footy_ev.backtest.walkforward import run_backtest

    con = duckdb.connect(":memory:")
    # Apply minimal schema so run_backtest can check the registry before any DB ops.
    con.execute(
        """
        CREATE TABLE backtest_runs (
            run_id VARCHAR PRIMARY KEY,
            model_version VARCHAR,
            league VARCHAR,
            train_min_seasons INTEGER,
            step_days INTEGER,
            started_at TIMESTAMP,
            status VARCHAR
        )
        """
    )
    with pytest.raises(ValueError, match="unknown model_version"):
        run_backtest(con, "EPL", model_version="bogus_v99")
