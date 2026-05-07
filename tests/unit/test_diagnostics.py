"""Unit tests for eval.diagnostics (Phase 2 step 2).

Covers:
  1. _rehydrate_booster round-trip preserves predict_proba.
  2. feature_sanity returns the expected aggregate keys.
  3. shap_importance returns one row per feature, descending mean_abs_shap.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import duckdb
import numpy as np
import pandas as pd
import xgboost as xgb

from footy_ev.db import apply_migrations
from footy_ev.eval.diagnostics import (
    _rehydrate_booster,
    feature_sanity,
    shap_importance,
)
from footy_ev.features.assembler import FEATURE_NAMES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_fixtures_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create v_fixtures_epl as a TABLE (not a view) so the diagnostics can
    read it from the same handle without apply_views()."""
    con.execute(
        """
        CREATE TABLE v_fixtures_epl (
            league         VARCHAR,
            season         VARCHAR,
            fixture_id     VARCHAR,
            kickoff_utc    TIMESTAMP,
            home_team_id   VARCHAR,
            away_team_id   VARCHAR,
            status         VARCHAR,
            home_score_ft  INTEGER,
            away_score_ft  INTEGER,
            home_xg        DOUBLE,
            away_xg        DOUBLE
        )
        """
    )


def _seed_two_teams_history(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Seed enough fixtures for both teams to have rolling history.
    Returns the list of fixture_ids in chronological order."""
    rows = []
    fids: list[str] = []
    base = datetime(2020, 8, 1)
    for i in range(20):
        fid = f"fix-{i:03d}"
        fids.append(fid)
        kickoff = base + timedelta(days=i * 7)
        # Alternate home/away so both teams accrue rolling stats
        if i % 2 == 0:
            h, a, hg, ag, hxg, axg = "team_a", "team_b", 2, 1, 1.7, 1.0
        else:
            h, a, hg, ag, hxg, axg = "team_b", "team_a", 1, 2, 1.1, 1.6
        rows.append(("EPL", "2020-2021", fid, kickoff, h, a, "final", hg, ag, hxg, axg))
    con.executemany(
        "INSERT INTO v_fixtures_epl VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return fids


def _insert_skellam_predictions(
    con: duckdb.DuckDBPyConnection,
    skellam_run_id: str,
    fixture_ids: list[str],
    as_of: datetime,
) -> None:
    """Insert a synthetic xG-Skellam over/under prediction per fixture."""
    rows = []
    for i, fid in enumerate(fixture_ids):
        # Spread p_over from 0.30 to 0.70 — clearly NOT the COALESCE default
        p_over = 0.30 + 0.40 * (i / max(1, len(fixture_ids) - 1))
        for sel, p in [("over", p_over), ("under", 1 - p_over)]:
            rows.append(
                (
                    str(uuid4()),
                    fid,
                    "ou_2.5",
                    sel,
                    p,
                    p,
                    None,
                    "xg_skellam_v1",
                    "fhash",
                    as_of,
                    datetime.now(),
                    skellam_run_id,
                )
            )
    con.executemany(
        """
        INSERT INTO model_predictions (
            prediction_id, fixture_id, market, selection, p_raw, p_calibrated,
            sigma_p, model_version, features_hash, as_of, generated_at, run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_backtest_run(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    step_days: int = 30,
) -> None:
    con.execute(
        """
        INSERT INTO backtest_runs (
            run_id, model_version, league, train_min_seasons, step_days,
            started_at, completed_at, status
        ) VALUES (?, 'xgb_ou25_v1', 'EPL', 3, ?, ?, ?, 'complete')
        """,
        [run_id, step_days, started_at, completed_at],
    )


def _fit_real_booster(
    feature_names: list[str], n_train: int = 200, seed: int = 0
) -> tuple[str, xgb.XGBClassifier]:
    """Fit a small XGBClassifier on synthetic data and return its booster_json."""
    rng = np.random.default_rng(seed)
    n_feat = len(feature_names)
    X = rng.uniform(size=(n_train, n_feat))
    # First feature drives the label, rest noise — gives SHAP a clear ranking
    y = (X[:, 0] + 0.1 * rng.standard_normal(n_train) > 0.5).astype(np.int8)
    clf = xgb.XGBClassifier(
        n_estimators=20,
        max_depth=3,
        learning_rate=0.1,
        objective="binary:logistic",
        verbosity=0,
        random_state=seed,
    )
    clf.fit(pd.DataFrame(X, columns=feature_names), y)
    return clf.get_booster().save_raw(raw_format="json").decode("utf-8"), clf


def _insert_xgb_fit(
    con: duckdb.DuckDBPyConnection,
    fit_id: str,
    skellam_run_id: str,
    as_of: datetime,
    fitted_at: datetime,
    feature_names: list[str],
    booster_json: str,
    n_train: int,
) -> None:
    con.execute(
        """
        INSERT INTO xgb_fits (
            fit_id, league, as_of, model_version, xg_skellam_run_id, n_train,
            n_estimators, max_depth, learning_rate, feature_names, booster_json,
            train_log_loss, fitted_at
        ) VALUES (?, 'EPL', ?, 'xgb_ou25_v1', ?, ?, 20, 3, 0.1, ?, ?, 0.5, ?)
        """,
        [fit_id, as_of, skellam_run_id, n_train, feature_names, booster_json, fitted_at],
    )


def _insert_xgb_predictions(
    con: duckdb.DuckDBPyConnection,
    xgb_run_id: str,
    fixture_ids: list[str],
    as_of: datetime,
) -> None:
    rows = []
    for fid in fixture_ids:
        for sel, p in [("over", 0.55), ("under", 0.45)]:
            rows.append(
                (
                    str(uuid4()),
                    fid,
                    "ou_2.5",
                    sel,
                    p,
                    p,
                    None,
                    "xgb_ou25_v1",
                    "fhash",
                    as_of,
                    datetime.now(),
                    xgb_run_id,
                )
            )
    con.executemany(
        """
        INSERT INTO model_predictions (
            prediction_id, fixture_id, market, selection, p_raw, p_calibrated,
            sigma_p, model_version, features_hash, as_of, generated_at, run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rehydrate_booster_round_trip() -> None:
    """A booster saved as JSON, rehydrated, predicts the same probabilities."""
    feature_names = ["f0", "f1", "f2"]
    booster_json, clf = _fit_real_booster(feature_names, n_train=120, seed=1)

    booster = _rehydrate_booster(booster_json)

    rng = np.random.default_rng(99)
    X = rng.uniform(size=(10, 3))
    X_pd = pd.DataFrame(X, columns=feature_names)
    p_orig = clf.predict_proba(X_pd)[:, 1]
    dmat = xgb.DMatrix(X_pd)
    p_rehydrated = booster.predict(dmat)
    np.testing.assert_allclose(p_orig, p_rehydrated, rtol=1e-5, atol=1e-7)


def test_feature_sanity_returns_aggregate_stats() -> None:
    """Synthetic XGBoost run produces well-distributed xg_skellam_p_over;
    feature_sanity reports min/max/mean and frac_at_default."""
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    _create_fixtures_table(con)
    fids = _seed_two_teams_history(con)

    # Use only fixtures 10..19 as test fixtures (10 prior matches gives enough rolling history)
    test_ids = fids[10:20]
    as_of = datetime(2020, 11, 1)

    skellam_run_id = "skellam-test-run"
    _insert_skellam_predictions(con, skellam_run_id, test_ids, as_of - timedelta(days=1))

    started = datetime(2026, 5, 6, 12, 0, 0)
    completed = datetime(2026, 5, 6, 12, 5, 0)
    xgb_run_id = "xgb-test-run"
    _insert_backtest_run(con, xgb_run_id, started, completed, step_days=30)

    feature_names = list(FEATURE_NAMES) + ["audit_noise"]
    booster_json, _ = _fit_real_booster(feature_names, n_train=200)
    _insert_xgb_fit(
        con,
        fit_id="fit-1",
        skellam_run_id=skellam_run_id,
        as_of=as_of,
        fitted_at=started + timedelta(seconds=30),
        feature_names=feature_names,
        booster_json=booster_json,
        n_train=200,
    )
    _insert_xgb_predictions(con, xgb_run_id, test_ids, as_of)

    stats = feature_sanity(con, xgb_run_id)
    assert stats["xgb_run_id"] == xgb_run_id
    assert stats["xg_skellam_run_id"] == skellam_run_id
    assert stats["n_rows"] == len(test_ids)
    # We seeded the Skellam predictions with values in [0.30, 0.70] — none at 0.5 default.
    # Spec uses linspace(0.30, 0.70, 10); element 4 happens to land exactly at 0.5.
    assert stats["frac_at_default"] <= 0.2
    assert 0.25 <= stats["min"] <= 0.35
    assert 0.65 <= stats["max"] <= 0.75
    assert 0.45 <= stats["mean"] <= 0.55


def test_shap_importance_returns_per_feature_ranking() -> None:
    """shap_importance returns one row per feature_name, sorted descending."""
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    _create_fixtures_table(con)
    fids = _seed_two_teams_history(con)

    test_ids = fids[10:20]
    as_of = datetime(2020, 11, 1)
    skellam_run_id = "skellam-test-run"
    _insert_skellam_predictions(con, skellam_run_id, test_ids, as_of - timedelta(days=1))

    started = datetime(2026, 5, 6, 13, 0, 0)
    completed = datetime(2026, 5, 6, 13, 5, 0)
    xgb_run_id = "xgb-test-shap"
    _insert_backtest_run(con, xgb_run_id, started, completed, step_days=30)

    feature_names = list(FEATURE_NAMES) + ["audit_noise"]
    booster_json, _ = _fit_real_booster(feature_names, n_train=200, seed=2)
    _insert_xgb_fit(
        con,
        fit_id="fit-shap",
        skellam_run_id=skellam_run_id,
        as_of=as_of,
        fitted_at=started + timedelta(seconds=30),
        feature_names=feature_names,
        booster_json=booster_json,
        n_train=200,
    )
    _insert_xgb_predictions(con, xgb_run_id, test_ids, as_of)

    ranking = shap_importance(con, xgb_run_id, fold_idx=-1)
    assert ranking.height == len(feature_names)
    assert set(ranking["feature_name"].to_list()) == set(feature_names)
    # mean_abs_shap is non-negative and sorted descending
    vals = ranking["mean_abs_shap"].to_list()
    assert all(v >= 0 for v in vals)
    assert vals == sorted(vals, reverse=True)
