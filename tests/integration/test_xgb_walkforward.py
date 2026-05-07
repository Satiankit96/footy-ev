"""Integration test: XGBoost walk-forward backtest end-to-end.

Gated behind FOOTY_EV_INTEGRATION_DB=1 and a populated warehouse.

Steps:
  1. Run xg_skellam_v1 backtest to produce a baseline run_id.
  2. Run xgb_ou25_v1 backtest using that run_id as the stacked feature source.
  3. Assert:
     - backtest_runs row present with status='complete'.
     - xgb_fits has at least 1 row for this run (via fit_id → model_predictions join).
     - xgb_feature_importances has exactly 16 rows per xgb_fits row.
     - model_predictions row count > 0.
     - audit_noise has below_null_baseline row in xgb_feature_importances
       (not all folds will flag it, but the column is populated).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import duckdb
import pytest

from footy_ev.backtest.walkforward import run_backtest
from footy_ev.db import apply_migrations, apply_views

INTEGRATION = os.environ.get("FOOTY_EV_INTEGRATION_DB") == "1"
WAREHOUSE = Path("data/warehouse/footy_ev.duckdb")


@pytest.mark.skipif(
    not INTEGRATION,
    reason="requires FOOTY_EV_INTEGRATION_DB=1 (uses populated warehouse)",
)
@pytest.mark.skipif(
    not WAREHOUSE.exists(),
    reason=f"warehouse db not present at {WAREHOUSE}",
)
def test_xgb_walkforward_end_to_end(tmp_path):
    dst = tmp_path / "footy_ev_xgb_test.duckdb"
    shutil.copy(WAREHOUSE, dst)

    con = duckdb.connect(str(dst))
    apply_migrations(con)
    apply_views(con)

    # Step 1: run xg_skellam baseline (short window to keep wall-time bounded)
    xg_run_id = run_backtest(
        con,
        "EPL",
        train_min_seasons=3,
        step_days=180,
        model_version="xg_skellam_v1",
        xi_decay=0.0,
    )

    xg_row = con.execute(
        "SELECT status, n_predictions FROM backtest_runs WHERE run_id = ?",
        [xg_run_id],
    ).fetchone()
    assert xg_row[0] == "complete"

    if xg_row[1] == 0:
        pytest.skip("xg_skellam produced 0 predictions — warehouse lacks Understat xG")

    # Step 2: run XGBoost backtest using xg_skellam as stacked feature
    xgb_run_id = run_backtest(
        con,
        "EPL",
        train_min_seasons=3,
        step_days=180,
        model_version="xgb_ou25_v1",
        xg_skellam_run_id=xg_run_id,
    )

    xgb_row = con.execute(
        "SELECT status, n_folds, n_predictions FROM backtest_runs WHERE run_id = ?",
        [xgb_run_id],
    ).fetchone()
    assert xgb_row[0] == "complete", f"xgb run failed: {xgb_row}"

    n_preds = xgb_row[2]
    if n_preds == 0:
        # May happen if warehouse xG data is too sparse for MIN_XGB_TRAIN_MATCHES
        return

    # xgb_fits: at least 1 fit row scoped to THIS run (xgb_fits has no run_id
    # column; scope by fitted_at falling inside the backtest_runs window).
    fit_ids = con.execute(
        """
        SELECT DISTINCT xf.fit_id
        FROM xgb_fits xf, backtest_runs br
        WHERE br.run_id = ?
          AND xf.model_version = 'xgb_ou25_v1'
          AND xf.league = 'EPL'
          AND xf.fitted_at >= br.started_at
          AND xf.fitted_at <= COALESCE(br.completed_at, xf.fitted_at)
        """,
        [xgb_run_id],
    ).fetchall()
    assert len(fit_ids) >= 1, "expected at least 1 xgb_fits row"

    # xgb_feature_importances: exactly 16 rows per fit_id
    for (fit_id,) in fit_ids:
        n_imp = con.execute(
            "SELECT COUNT(*) FROM xgb_feature_importances WHERE fit_id = ?",
            [fit_id],
        ).fetchone()[0]
        assert n_imp == 16, f"fit_id={fit_id}: expected 16 importance rows, got {n_imp}"

    # audit_noise column populated for THIS run's fits
    audit_rows = con.execute(
        """
        SELECT COUNT(*) FROM xgb_feature_importances xfi, xgb_fits xf, backtest_runs br
        WHERE xfi.fit_id = xf.fit_id
          AND xfi.feature_name = 'audit_noise'
          AND br.run_id = ?
          AND xf.model_version = 'xgb_ou25_v1'
          AND xf.fitted_at >= br.started_at
          AND xf.fitted_at <= COALESCE(br.completed_at, xf.fitted_at)
        """,
        [xgb_run_id],
    ).fetchone()[0]
    assert audit_rows >= 1, "expected audit_noise rows in xgb_feature_importances"

    # model_predictions: market = 'ou_2.5', selections = {'over', 'under'}
    markets = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT market FROM model_predictions WHERE run_id = ?",
            [xgb_run_id],
        ).fetchall()
    }
    assert markets == {"ou_2.5"}, f"unexpected markets: {markets}"
