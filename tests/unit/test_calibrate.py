"""Unit tests for walk-forward isotonic calibration.

Builds a synthetic in-memory warehouse (apply_migrations + apply_views are
overkill for these scenarios — we create just the tables/views that
calibrate.py reads), seeds model_predictions and a minimal v_fixtures_epl,
then exercises the walk-forward logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import duckdb
import numpy as np
import pytest

from footy_ev.eval.calibrate import (
    MIN_TRAIN_N,
    SELECTIONS,
    fit_isotonic_walk_forward,
    persist_calibration_fits,
)


def _make_test_db() -> duckdb.DuckDBPyConnection:
    """Minimal schema: model_predictions + v_fixtures_epl (as a TABLE for ease)."""
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE model_predictions (
            prediction_id  VARCHAR PRIMARY KEY,
            run_id         VARCHAR NOT NULL,
            fixture_id     VARCHAR NOT NULL,
            market         VARCHAR NOT NULL DEFAULT '1x2',
            selection      VARCHAR NOT NULL,
            p_raw          DOUBLE NOT NULL,
            p_calibrated   DOUBLE NOT NULL,
            sigma_p        DOUBLE,
            model_version  VARCHAR,
            features_hash  VARCHAR,
            as_of          TIMESTAMP NOT NULL,
            generated_at   TIMESTAMP,
            run_id_dup     VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE v_fixtures_epl (
            fixture_id      VARCHAR PRIMARY KEY,
            result_ft       VARCHAR,
            home_score_ft   INTEGER,
            away_score_ft   INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE calibration_fits (
            fit_id            VARCHAR PRIMARY KEY,
            run_id            VARCHAR,
            market            VARCHAR,
            selection         VARCHAR,
            iso_x             DOUBLE[],
            iso_y             DOUBLE[],
            n_train           INTEGER,
            n_test            INTEGER,
            brier_raw         DOUBLE,
            brier_calibrated  DOUBLE,
            fitted_at         TIMESTAMP
        )
    """)
    return con


def _seed_predictions(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    folds: list[tuple[datetime, list[tuple[str, str, float, str]]]],
) -> None:
    """Seed (as_of, [(fixture_id, selection, p_raw, result_ft), ...]) per fold."""
    fixtures_seen: dict[str, str] = {}
    for as_of, rows in folds:
        for fid, sel, p_raw, result_ft in rows:
            fixtures_seen[fid] = result_ft
            con.execute(
                "INSERT INTO model_predictions (prediction_id, run_id, fixture_id, "
                "selection, p_raw, p_calibrated, as_of) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [str(uuid.uuid4()), run_id, fid, sel, p_raw, p_raw, as_of],
            )
    for fid, result in fixtures_seen.items():
        con.execute(
            "INSERT OR IGNORE INTO v_fixtures_epl (fixture_id, result_ft) VALUES (?, ?)",
            [fid, result],
        )


def test_first_fold_identity_passthrough():
    """Fold 1 has no prior train data → p_calibrated == p_raw."""
    con = _make_test_db()
    run_id = "r1"
    base = datetime(2020, 1, 1)
    fold1 = (base, [(f"f{i}", "home", 0.5, "H") for i in range(50)])
    _seed_predictions(con, run_id, [fold1])
    calibrated, state = fit_isotonic_walk_forward(con, run_id)
    assert len(calibrated) == 50
    for _pred_id, p_cal in calibrated.items():
        # All inputs were 0.5; passthrough means p_cal == 0.5
        assert p_cal == pytest.approx(0.5, abs=1e-12)


def test_min_train_n_threshold_respected():
    """Fold k has fewer than MIN_TRAIN_N prior predictions per selection → passthrough."""
    con = _make_test_db()
    run_id = "r2"
    base = datetime(2020, 1, 1)

    # Fold 1: 30 home predictions (below threshold 500)
    fold1 = (base, [(f"a{i}", "home", 0.5, "H") for i in range(30)])
    # Fold 2: 50 home predictions
    fold2 = (base + timedelta(days=7), [(f"b{i}", "home", 0.5, "H") for i in range(50)])
    _seed_predictions(con, run_id, [fold1, fold2])

    calibrated, _state = fit_isotonic_walk_forward(con, run_id, min_train_n=MIN_TRAIN_N)
    # Even fold 2's prior train (30) is < 500 → passthrough
    assert all(v == pytest.approx(0.5, abs=1e-12) for v in calibrated.values())


def test_isotonic_kicks_in_when_threshold_met():
    """Sufficient prior data → isotonic fit applied; calibrated != raw on miscalibrated input."""
    con = _make_test_db()
    run_id = "r3"
    base = datetime(2020, 1, 1)

    # Build a strongly miscalibrated prior: model says 0.7 but only 30% win.
    rng = np.random.default_rng(0)
    fold1_rows = []
    for i in range(150):
        result = "H" if rng.random() < 0.30 else "A"
        fold1_rows.append((f"p1-{i}", "home", 0.70, result))
    fold1 = (base, fold1_rows)

    # Fold 2: same 0.70 raw probability
    fold2_rows = [(f"p2-{i}", "home", 0.70, "A") for i in range(20)]
    fold2 = (base + timedelta(days=7), fold2_rows)

    _seed_predictions(con, run_id, [fold1, fold2])

    calibrated, state = fit_isotonic_walk_forward(con, run_id, min_train_n=100)
    # Fold 1 still passthrough (no prior). Check fold 2 specifically.
    fold2_fixture_ids = [r[0] for r in fold2_rows]
    fold2_pred_ids = [
        row[0]
        for row in con.execute(
            "SELECT prediction_id FROM model_predictions WHERE fixture_id IN ("
            + ",".join(["?"] * len(fold2_fixture_ids))
            + ") AND selection = 'home'",
            fold2_fixture_ids,
        ).fetchall()
    ]
    fold2_calibrated = [calibrated[pid] for pid in fold2_pred_ids]
    # Should be calibrated DOWN toward ~0.30 (training showed 30% empirical rate at p_raw=0.7)
    avg_fold2 = sum(fold2_calibrated) / len(fold2_calibrated)
    assert avg_fold2 < 0.50, (
        f"isotonic should pull 0.70 toward empirical 0.30; got mean={avg_fold2:.3f}"
    )
    # State for 'home' selection populated
    assert "home" in state
    assert state["home"]["n_train"] == 170  # 150 + 20
    assert state["home"]["brier_raw"] >= state["home"]["brier_calibrated"] - 1e-9


def test_persist_calibration_fits_writes_three_rows():
    """End-to-end: walk-forward + persist creates one row per selection present."""
    con = _make_test_db()
    run_id = "r4"
    base = datetime(2020, 1, 1)
    rng = np.random.default_rng(1)

    folds = []
    for fold_idx in range(5):
        as_of = base + timedelta(days=7 * fold_idx)
        rows = []
        for j in range(40):
            fid = f"fld{fold_idx}-{j}"
            result = rng.choice(["H", "D", "A"])
            for sel, p in (("home", 0.5), ("draw", 0.25), ("away", 0.25)):
                rows.append((fid, sel, p, result))
        folds.append((as_of, rows))
    _seed_predictions(con, run_id, folds)

    calibrated, state = fit_isotonic_walk_forward(con, run_id, min_train_n=50)
    persist_calibration_fits(con, run_id, state)
    n_fits = con.execute(
        "SELECT COUNT(*) FROM calibration_fits WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    assert n_fits == 3
    sels = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT selection FROM calibration_fits WHERE run_id = ?",
            [run_id],
        ).fetchall()
    }
    assert sels == set(SELECTIONS)


def test_empty_run_returns_empty_state():
    """Run with no predictions yields empty mapping and empty state, no crash."""
    con = _make_test_db()
    calibrated, state = fit_isotonic_walk_forward(con, "nonexistent")
    assert calibrated == {}
    assert state == {}
    persist_calibration_fits(con, "nonexistent", state)  # no-op, no crash
    assert (
        con.execute(
            "SELECT COUNT(*) FROM calibration_fits WHERE run_id = ?", ["nonexistent"]
        ).fetchone()[0]
        == 0
    )


def test_isotonic_passthrough_at_500():
    """With 400 prior predictions per selection, fold 2 still gets passthrough (< MIN_TRAIN_N=500)."""
    con = _make_test_db()
    run_id = "r6"
    base = datetime(2020, 1, 1)
    assert MIN_TRAIN_N == 500, f"expected MIN_TRAIN_N=500, got {MIN_TRAIN_N}"

    rng = np.random.default_rng(42)
    fold1_rows = [
        (f"q1-{i}", "home", 0.60, "H" if rng.random() < 0.30 else "A") for i in range(400)
    ]
    fold1 = (base, fold1_rows)
    fold2_rows = [(f"q2-{i}", "home", 0.60, "A") for i in range(50)]
    fold2 = (base + timedelta(days=7), fold2_rows)
    _seed_predictions(con, run_id, [fold1, fold2])

    calibrated, _ = fit_isotonic_walk_forward(con, run_id)
    # fold 2 has 400 prior predictions — still below 500 → passthrough
    fold2_fixture_ids = [r[0] for r in fold2_rows]
    fold2_pred_ids = [
        row[0]
        for row in con.execute(
            "SELECT prediction_id FROM model_predictions WHERE fixture_id IN ("
            + ",".join(["?"] * len(fold2_fixture_ids))
            + ") AND selection = 'home'",
            fold2_fixture_ids,
        ).fetchall()
    ]
    fold2_calibrated = [calibrated[pid] for pid in fold2_pred_ids]
    assert all(v == pytest.approx(0.60, abs=1e-12) for v in fold2_calibrated)
