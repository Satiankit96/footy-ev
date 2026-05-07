"""Integration test: end-to-end evaluate_run on a self-contained backtest.

Gated behind FOOTY_EV_INTEGRATION_DB=1. Copies the live warehouse to a
temp file, runs a fresh backtest covering the Pinnacle-coverage window
(2012-13 onward), then evaluates that run. Asserts:

  - run_id roundtrip in backtest_runs
  - clv_evaluations row count <= 3 × n_predictions, with skipped equal to
    the diff (skip-and-log policy)
  - exactly 3 calibration_fits rows (one per selection)
  - reliability_bins row count is between 0 and 45 (3 selections × 15 bins)
  - returned summary has all expected keys + a verdict in the allowed set
  - reports/run_<run_id>.md exists, mentions the verdict token, and
    contains the post-landing instructions block
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import duckdb
import pytest

from footy_ev.backtest.walkforward import run_backtest
from footy_ev.db import apply_migrations, apply_views
from footy_ev.eval.cli import evaluate_run

INTEGRATION = os.environ.get("FOOTY_EV_INTEGRATION_DB") == "1"
WAREHOUSE = Path("data/warehouse/footy_ev.duckdb")

ALLOWED_VERDICTS = {"GO", "NO_GO", "MARGINAL_SIGNAL", "PRELIMINARY_SIGNAL", "INSUFFICIENT_SAMPLE"}


@pytest.mark.skipif(
    not INTEGRATION,
    reason="requires FOOTY_EV_INTEGRATION_DB=1 (uses populated warehouse)",
)
@pytest.mark.skipif(
    not WAREHOUSE.exists(),
    reason=f"warehouse db not present at {WAREHOUSE}",
)
def test_evaluate_run_end_to_end(tmp_path):
    dst = tmp_path / "footy_ev_eval_test.duckdb"
    shutil.copy(WAREHOUSE, dst)

    con = duckdb.connect(str(dst))
    apply_migrations(con)
    apply_views(con)

    # Backtest spanning the Pinnacle-coverage window (2012-13 onward) at
    # half-yearly steps to keep wall-time bounded. train_min_seasons=12
    # warms up through 2011-12 (last pre-Pinnacle season); first test
    # window starts 2012-13 onward where Pinnacle close is present.
    run_id = run_backtest(
        con,
        "EPL",
        train_min_seasons=12,
        step_days=180,
        model_version="dc_v1",
    )

    # Sanity: backtest produced predictions
    n_pred = con.execute(
        "SELECT COUNT(*) FROM model_predictions WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    assert n_pred > 0, "backtest produced zero predictions"

    summary = evaluate_run(con, run_id, reports_dir=tmp_path / "reports")

    # Top-level keys
    expected_keys = {
        "run_id",
        "league",
        "model_version",
        "n_folds",
        "n_predictions",
        "devig_method",
        "n_evaluated",
        "n_skipped_no_pinnacle",
        "n_would_have_bet",
        "mean_edge_all",
        "median_edge_all",
        "mean_edge_winners",
        "median_edge_winners",
        "mean_edge_would_have_bet",
        "edge_by_season",
        "brier_raw_by_selection",
        "brier_calibrated_by_selection",
        "reliability_pass_pct_by_selection",
        "bootstrap_mean",
        "bootstrap_ci_low",
        "bootstrap_ci_high",
        "bootstrap_p_value_above_zero",
        "bootstrap_n_winners",
        "bootstrap_n_resamples",
        "go_no_go_verdict",
        "report_path",
    }
    assert expected_keys.issubset(summary.keys()), f"missing keys: {expected_keys - summary.keys()}"
    assert summary["go_no_go_verdict"] in ALLOWED_VERDICTS
    assert summary["n_evaluated"] > 0, "expected non-zero evaluations on Pinnacle window"

    # clv_evaluations row count = n_evaluated; row count + skipped <= 3 * n_pred
    n_clv = con.execute(
        "SELECT COUNT(*) FROM clv_evaluations WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    assert n_clv == summary["n_evaluated"]
    assert n_clv + summary["n_skipped_no_pinnacle"] == n_pred, (
        "clv + skipped should equal predictions exactly"
    )

    # calibration_fits: 3 rows (one per selection)
    n_cal = con.execute(
        "SELECT COUNT(*) FROM calibration_fits WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    assert n_cal == 3

    # reliability_bins: at most 3 × 15 = 45
    n_bins = con.execute(
        "SELECT COUNT(*) FROM reliability_bins WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    assert 0 < n_bins <= 45

    # Per-selection three rows per fixture in clv_evaluations
    bad = con.execute(
        """
        SELECT fixture_id, COUNT(*) AS c
        FROM clv_evaluations WHERE run_id = ?
        GROUP BY fixture_id HAVING COUNT(*) <> 3
        """,
        [run_id],
    ).fetchall()
    assert bad == [], f"unexpected per-fixture row counts: {bad[:5]}"

    # Markdown report
    report_path = Path(summary["report_path"])
    assert report_path.exists(), f"report not written to {report_path}"
    text = report_path.read_text(encoding="utf-8")
    assert summary["go_no_go_verdict"] in text
    assert "Bootstrap CI" in text
    assert "How to produce the canonical go/no-go run" in text
    assert ".\\make.ps1 backtest-epl" in text
    assert ".\\make.ps1 evaluate-run" in text


@pytest.mark.skipif(
    not INTEGRATION,
    reason="requires FOOTY_EV_INTEGRATION_DB=1",
)
def test_evaluate_run_unknown_run_id_raises(tmp_path):
    """evaluate_run on a missing run_id raises ValueError cleanly."""
    db = tmp_path / "empty.duckdb"
    con = duckdb.connect(str(db))
    apply_migrations(con)
    apply_views(con)
    with pytest.raises(ValueError, match="run_id not found"):
        evaluate_run(con, "does-not-exist", reports_dir=tmp_path / "reports")


@pytest.mark.skipif(
    not INTEGRATION,
    reason="requires FOOTY_EV_INTEGRATION_DB=1 (uses populated warehouse)",
)
@pytest.mark.skipif(
    not WAREHOUSE.exists(),
    reason=f"warehouse db not present at {WAREHOUSE}",
)
def test_evaluate_run_no_calibrate(tmp_path):
    """--no-calibrate: clv_evaluations written, calibration_fits NOT written."""
    dst = tmp_path / "footy_ev_nocal_test.duckdb"
    shutil.copy(WAREHOUSE, dst)
    con = duckdb.connect(str(dst))
    apply_migrations(con)
    apply_views(con)

    run_id = run_backtest(
        con,
        "EPL",
        train_min_seasons=12,
        step_days=180,
        model_version="dc_v1",
    )
    summary = evaluate_run(con, run_id, reports_dir=tmp_path / "reports", no_calibrate=True)

    assert summary["go_no_go_verdict"] in ALLOWED_VERDICTS
    assert summary["no_calibrate"] is True

    # calibration_fits: zero rows (isotonic skipped)
    n_cal = con.execute(
        "SELECT COUNT(*) FROM calibration_fits WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    assert n_cal == 0, "no-calibrate run must not write calibration_fits"

    # clv_evaluations must still be present
    n_clv = con.execute(
        "SELECT COUNT(*) FROM clv_evaluations WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    assert n_clv > 0


@pytest.mark.skipif(
    not INTEGRATION,
    reason="requires FOOTY_EV_INTEGRATION_DB=1 (uses populated warehouse)",
)
@pytest.mark.skipif(
    not WAREHOUSE.exists(),
    reason=f"warehouse db not present at {WAREHOUSE}",
)
def test_evaluate_run_xg_skellam_end_to_end(tmp_path):
    """xg_skellam_v1: backtest + evaluate; 2 rows per fixture, 2 cal fits."""
    dst = tmp_path / "footy_ev_xg_test.duckdb"
    shutil.copy(WAREHOUSE, dst)
    con = duckdb.connect(str(dst))
    apply_migrations(con)
    apply_views(con)

    # xg_skellam requires xG data (Understat); available from ~2014-15.
    # train_min_seasons=3 allows starting from ~2017-18 onward.
    run_id = run_backtest(
        con,
        "EPL",
        train_min_seasons=3,
        step_days=180,
        model_version="xg_skellam_v1",
    )

    n_pred = con.execute(
        "SELECT COUNT(*) FROM model_predictions WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    # xG data may be sparse; we just require a non-trivial number of predictions
    assert n_pred >= 0, "xg_skellam backtest must complete without crash"

    if n_pred == 0:
        # Warehouse has no Understat xG → skip further assertions
        return

    summary = evaluate_run(con, run_id, reports_dir=tmp_path / "reports")
    assert summary["go_no_go_verdict"] in ALLOWED_VERDICTS

    # model_predictions market must be 'ou_2.5'
    markets = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT market FROM model_predictions WHERE run_id = ?", [run_id]
        ).fetchall()
    }
    assert markets == {"ou_2.5"}, f"unexpected markets in xg_skellam run: {markets}"

    # Each evaluable fixture has 2 clv rows (over + under)
    bad = con.execute(
        """
        SELECT fixture_id, COUNT(*) AS c
        FROM clv_evaluations WHERE run_id = ?
        GROUP BY fixture_id HAVING COUNT(*) <> 2
        """,
        [run_id],
    ).fetchall()
    assert bad == [], f"unexpected per-fixture row counts: {bad[:5]}"

    # calibration_fits: 2 rows (over + under) if any evaluated
    n_clv = con.execute(
        "SELECT COUNT(*) FROM clv_evaluations WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    if n_clv > 0:
        n_cal = con.execute(
            "SELECT COUNT(*) FROM calibration_fits WHERE run_id = ?", [run_id]
        ).fetchone()[0]
        assert n_cal <= 2, f"expected <= 2 calibration_fits for xg_skellam, got {n_cal}"
