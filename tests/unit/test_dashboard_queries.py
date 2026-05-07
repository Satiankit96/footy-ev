"""Smoke tests for dashboard.queries against an in-memory DuckDB.

Each test seeds minimal synthetic rows into the relevant tables and asserts
that the query function returns the expected schema and basic shape.
No Streamlit imports — pure Python.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import duckdb

from dashboard.queries import (
    available_markets,
    available_model_versions,
    available_seasons,
    clv_agg,
    clv_bets_count,
    clv_bets_df,
    cross_run_clv,
    edge_by_season,
    feature_importances_df,
    feature_stability_df,
    reliability_bins_df,
    run_meta,
    runs_list,
)
from footy_ev.db import apply_migrations

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    return con


def _seed_run(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    model_version: str = "xgb_ou25_v1",
    status: str = "complete",
) -> tuple[datetime, datetime]:
    started = datetime(2024, 8, 1, 10, 0, 0)
    completed = datetime(2024, 8, 1, 11, 0, 0)
    con.execute(
        """INSERT INTO backtest_runs
               (run_id, model_version, league, train_min_seasons, step_days,
                started_at, completed_at, n_folds, n_predictions, status)
           VALUES (?, ?, 'EPL', 3, 7, ?, ?, 5, 50, ?)""",
        [run_id, model_version, started, completed, status],
    )
    return started, completed


def _seed_clv(con: duckdb.DuckDBPyConnection, run_id: str, n: int = 20) -> None:
    rows = []
    for i in range(n):
        season = "2023-2024" if i < 10 else "2024-2025"
        fid = f"EPL|{season}|teamA|teamB|2024-0{(i % 9) + 1}-01"
        rows.append(
            (
                str(uuid4()),
                run_id,
                str(uuid4()),
                fid,
                "ou_2.5",
                "over",
                0.55,
                0.55,
                2.1,
                0.476,
                "shin",
                0.07 if i % 2 == 0 else -0.03,
                i % 2 == 0,  # is_winner alternates
                i % 3 == 0,  # would_have_bet every third
                datetime.now(),
            )
        )
    con.executemany(
        """INSERT INTO clv_evaluations
               (evaluation_id, run_id, prediction_id, fixture_id, market, selection,
                p_raw, p_calibrated, pinnacle_close_decimal, pinnacle_q_devigged,
                devig_method, edge_at_close, is_winner, would_have_bet, evaluated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )


def _seed_reliability(con: duckdb.DuckDBPyConnection, run_id: str) -> None:
    for idx in range(3):
        lo = idx * 0.1
        hi = lo + 0.1
        con.execute(
            """INSERT INTO reliability_bins
                   (run_id, market, selection, bin_idx, bin_lower, bin_upper,
                    n_in_bin, frac_pos, mean_pred, passes_2pp)
               VALUES (?, 'ou_2.5', 'over', ?, ?, ?, 10, 0.5, 0.5, TRUE)""",
            [run_id, idx, lo, hi],
        )


def _seed_xgb_fits(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    started: datetime,
    n_folds: int = 3,
) -> list[str]:
    fit_ids = []
    skellam_run = "ske-run-001"
    for i in range(n_folds):
        fit_id = str(uuid4())
        fit_ids.append(fit_id)
        as_of = datetime(2024, 1, 1) + timedelta(days=i * 7)
        fitted_at = started + timedelta(seconds=i * 10 + 5)
        con.execute(
            """INSERT INTO xgb_fits
                   (fit_id, league, as_of, model_version, xg_skellam_run_id,
                    n_train, n_estimators, max_depth, learning_rate,
                    feature_names, booster_json, train_log_loss, fitted_at)
               VALUES (?, 'EPL', ?, 'xgb_ou25_v1', ?, 100, 20, 3, 0.1,
                       ['f0','f1','audit_noise'], '{}', 0.5, ?)""",
            [fit_id, as_of, skellam_run, fitted_at],
        )
    return fit_ids


def _seed_importances(con: duckdb.DuckDBPyConnection, fit_ids: list[str]) -> None:
    for fit_id in fit_ids:
        for feat in ["f0", "f1", "audit_noise"]:
            con.execute(
                """INSERT INTO xgb_feature_importances
                       (fit_id, feature_name, importance_gain, permutation_importance,
                        perm_ci_low, perm_ci_high, below_null_baseline)
                   VALUES (?, ?, 0.1, 0.05, 0.0, 0.1, TRUE)""",
                [fit_id, feat],
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_runs_list_returns_all_runs() -> None:
    con = _make_con()
    run_id_1 = str(uuid4())
    run_id_2 = str(uuid4())
    _seed_run(con, run_id_1)
    _seed_run(con, run_id_2, model_version="xg_skellam_v1")
    df = runs_list(con)
    assert df.height == 2
    assert "run_id" in df.columns
    assert "model_version" in df.columns


def test_runs_list_empty_db_returns_zero_rows() -> None:
    con = _make_con()
    df = runs_list(con)
    assert df.height == 0


def test_run_meta_found() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    meta = run_meta(con, rid)
    assert meta is not None
    assert meta["run_id"] == rid
    assert meta["model_version"] == "xgb_ou25_v1"


def test_run_meta_not_found_returns_none() -> None:
    con = _make_con()
    assert run_meta(con, "nonexistent-run") is None


def test_clv_agg_no_data_returns_zeros() -> None:
    con = _make_con()
    result = clv_agg(con, "empty-run")
    assert result["n_evaluated"] == 0
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"


def test_clv_agg_with_data() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_clv(con, rid, n=30)
    result = clv_agg(con, rid)
    assert result["n_evaluated"] == 30
    assert result["verdict"] in {
        "INSUFFICIENT_SAMPLE",
        "PRELIMINARY_SIGNAL",
        "NO_GO",
        "MARGINAL_SIGNAL",
        "GO",
    }


def test_edge_by_season_schema() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_clv(con, rid, n=20)
    df = edge_by_season(con, rid)
    assert "season" in df.columns
    assert "mean_edge" in df.columns
    assert df.height >= 1


def test_reliability_bins_schema() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_reliability(con, rid)
    df = reliability_bins_df(con, rid)
    assert "market" in df.columns
    assert "bin_idx" in df.columns
    assert df.height == 3


def test_reliability_bins_empty_run() -> None:
    con = _make_con()
    df = reliability_bins_df(con, "no-run")
    assert df.height == 0


def test_feature_importances_schema() -> None:
    con = _make_con()
    rid = str(uuid4())
    started, _ = _seed_run(con, rid)
    fit_ids = _seed_xgb_fits(con, rid, started, n_folds=3)
    _seed_importances(con, fit_ids)
    df = feature_importances_df(con, rid)
    assert "fold_rank" in df.columns
    assert "feature_name" in df.columns
    assert "below_null_baseline" in df.columns
    assert df.height == 9  # 3 folds × 3 features


def test_feature_importances_no_run() -> None:
    con = _make_con()
    df = feature_importances_df(con, "no-run")
    assert df.height == 0


def test_clv_bets_df_pagination() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_clv(con, rid, n=25)
    df_p0 = clv_bets_df(con, rid, page=0, page_size=10)
    df_p1 = clv_bets_df(con, rid, page=1, page_size=10)
    df_p2 = clv_bets_df(con, rid, page=2, page_size=10)
    assert df_p0.height == 10
    assert df_p1.height == 10
    # Third page has the remaining 5 rows
    assert df_p2.height == 5
    # Total across three pages = 25
    assert df_p0.height + df_p1.height + df_p2.height == 25


def test_clv_bets_count() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_clv(con, rid, n=20)
    total = clv_bets_count(con, rid)
    assert total == 20
    whb_total = clv_bets_count(con, rid, would_have_bet_only=True)
    assert 0 <= whb_total <= 20


def test_cross_run_clv_returns_rows() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_clv(con, rid, n=20)
    df = cross_run_clv(con)
    assert df.height >= 1
    assert "run_id" in df.columns
    assert "mean_edge_winners" in df.columns


def test_available_seasons() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_clv(con, rid, n=20)
    seasons = available_seasons(con)
    assert len(seasons) >= 1
    assert all(isinstance(s, str) for s in seasons)


def test_available_markets() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid)
    _seed_clv(con, rid, n=5)
    markets = available_markets(con)
    assert "ou_2.5" in markets


def test_available_model_versions() -> None:
    con = _make_con()
    rid = str(uuid4())
    _seed_run(con, rid, model_version="xgb_ou25_v1")
    mvs = available_model_versions(con)
    assert "xgb_ou25_v1" in mvs


def test_feature_stability_schema() -> None:
    con = _make_con()
    rid = str(uuid4())
    started, _ = _seed_run(con, rid)
    fit_ids = _seed_xgb_fits(con, rid, started, n_folds=3)
    _seed_importances(con, fit_ids)
    df = feature_stability_df(con, rid)
    assert "fold_rank" in df.columns
    assert "feature_name" in df.columns
    assert "permutation_importance" in df.columns
    assert df.height == 9  # 3 folds × 3 features
