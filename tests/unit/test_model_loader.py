"""Unit tests for footy_ev.runtime.model_loader.

Tests:
  1. detect_production_run_id: returns run_id when qualifying run exists.
  2. detect_production_run_id: raises NoProductionModelError when no runs.
  3. _load_booster_artifacts: round-trips booster JSON; returns correct feature_names.
  4. load_production_scorer: returned score_fn is callable.
  5. load_production_scorer: raises NoProductionModelError for unknown run_id.
  6. Booster cache: second call for same run_id skips DB query (uses _BOOSTER_CACHE).
  7. score_fn: returns [] when fixture_ids is empty.
  8. score_fn: returns [] gracefully when build_feature_matrix raises.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import duckdb
import numpy as np
import pytest
import xgboost as xgb

from footy_ev.db import apply_migrations, apply_views
from footy_ev.runtime.model_loader import (
    _BOOSTER_CACHE,
    NoProductionModelError,
    _load_booster_artifacts,
    clear_booster_cache,
    detect_production_run_id,
    load_production_scorer,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Evict all cached boosters before each test."""
    clear_booster_cache()


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_migrations(c)
    apply_views(c)
    return c


def _insert_run(
    con: duckdb.DuckDBPyConnection,
    run_id: str = "run_xgb_001",
    status: str = "completed",
) -> None:
    started = datetime(2024, 1, 1, 0)
    completed = datetime(2024, 1, 1, 23, 59, 59)
    con.execute(
        """
        INSERT INTO backtest_runs
            (run_id, model_version, league, train_min_seasons, step_days,
             started_at, completed_at, n_folds, n_predictions, status)
        VALUES (?, 'xgb_ou25_v1', 'EPL', 3, 7, ?, ?, 4, 400, ?)
        """,
        [run_id, started, completed, status],
    )


def _make_booster_json() -> str:
    """Create a minimal binary:logistic booster JSON via XGBClassifier.fit."""
    rng = np.random.default_rng(42)
    n = 60
    X = rng.uniform(size=(n, 3))
    y = rng.integers(0, 2, size=n)
    import pandas as pd

    clf = xgb.XGBClassifier(n_estimators=5, max_depth=2, verbosity=0, objective="binary:logistic")
    clf.fit(pd.DataFrame(X, columns=["f0", "f1", "f2"]), y)
    return clf.get_booster().save_raw(raw_format="json").decode("utf-8")


def _insert_fit(
    con: duckdb.DuckDBPyConnection,
    run_id: str = "run_xgb_001",
    booster_json: str | None = None,
) -> None:
    if booster_json is None:
        booster_json = _make_booster_json()
    now = datetime(2024, 1, 1, 12)
    con.execute(
        """
        INSERT INTO xgb_fits
            (fit_id, league, as_of, model_version, xg_skellam_run_id,
             n_train, n_estimators, max_depth, learning_rate,
             feature_names, booster_json, train_log_loss, fitted_at)
        VALUES (?, 'EPL', ?, 'xgb_ou25_v1', 'run_skellam_001',
                500, 5, 2, 0.05, ?, ?, 0.65, ?)
        """,
        [f"fit_{run_id}", now, ["f0", "f1", "f2"], booster_json, now],
    )


# ---------------------------------------------------------------------------
# detect_production_run_id
# ---------------------------------------------------------------------------


def test_detect_production_run_id_returns_latest(con: duckdb.DuckDBPyConnection) -> None:
    _insert_run(con, "run_a")
    _insert_fit(con, "run_a")
    result = detect_production_run_id(con)
    assert result == "run_a"


def test_detect_production_run_id_no_runs_raises(con: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(NoProductionModelError, match="No completed xgb_ou25_v1"):
        detect_production_run_id(con)


def test_detect_production_run_id_ignores_failed_runs(
    con: duckdb.DuckDBPyConnection,
) -> None:
    _insert_run(con, "run_failed", status="failed")
    _insert_fit(con, "run_failed")
    with pytest.raises(NoProductionModelError):
        detect_production_run_id(con)


# ---------------------------------------------------------------------------
# _load_booster_artifacts
# ---------------------------------------------------------------------------


def test_load_booster_artifacts_round_trip(con: duckdb.DuckDBPyConnection) -> None:
    _insert_run(con)
    booster_json = _make_booster_json()
    _insert_fit(con, booster_json=booster_json)

    booster, feature_names, xg_skellam_run_id = _load_booster_artifacts(con, "run_xgb_001")

    assert isinstance(booster, xgb.Booster)
    assert feature_names == ["f0", "f1", "f2"]
    assert xg_skellam_run_id == "run_skellam_001"


def test_load_booster_artifacts_unknown_run_raises(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(NoProductionModelError, match="not found in backtest_runs"):
        _load_booster_artifacts(con, "nonexistent")


def test_load_booster_artifacts_cached_on_second_call(
    con: duckdb.DuckDBPyConnection,
) -> None:
    _insert_run(con)
    _insert_fit(con)

    _load_booster_artifacts(con, "run_xgb_001")
    assert "run_xgb_001" in _BOOSTER_CACHE

    # Second call with a closed connection should still work (served from cache)
    closed = duckdb.connect(":memory:")
    closed.close()
    booster, _, _ = _load_booster_artifacts(closed, "run_xgb_001")
    assert isinstance(booster, xgb.Booster)


# ---------------------------------------------------------------------------
# load_production_scorer
# ---------------------------------------------------------------------------


def test_load_production_scorer_returns_callable(
    con: duckdb.DuckDBPyConnection,
) -> None:
    _insert_run(con)
    _insert_fit(con)
    score_fn = load_production_scorer(con, "run_xgb_001")
    assert callable(score_fn)


def test_load_production_scorer_unknown_run_raises(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(NoProductionModelError):
        load_production_scorer(con, "ghost_run")


# ---------------------------------------------------------------------------
# score_fn behaviour
# ---------------------------------------------------------------------------


def test_score_fn_empty_fixture_ids(con: duckdb.DuckDBPyConnection) -> None:
    _insert_run(con)
    _insert_fit(con)
    score_fn = load_production_scorer(con, "run_xgb_001")
    result = score_fn([], datetime(2024, 6, 1))
    assert result == []


def test_score_fn_returns_empty_when_build_feature_matrix_raises(
    con: duckdb.DuckDBPyConnection,
) -> None:
    _insert_run(con)
    _insert_fit(con)
    score_fn = load_production_scorer(con, "run_xgb_001")

    with patch(
        "footy_ev.runtime.model_loader.build_feature_matrix",
        side_effect=RuntimeError("db error"),
    ):
        result = score_fn(["fixture_123"], datetime(2024, 6, 1))
    assert result == []


def test_score_fn_returns_dicts_when_feature_matrix_has_rows(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Mock build_feature_matrix to return one row; verify score_fn dict shape."""
    import polars as pl

    _insert_run(con)
    _insert_fit(con)
    score_fn = load_production_scorer(con, "run_xgb_001")

    fake_df = pl.DataFrame({"fixture_id": ["evt_42"], "f0": [1.2], "f1": [0.8], "f2": [0.5]})

    with patch(
        "footy_ev.runtime.model_loader.build_feature_matrix",
        return_value=fake_df,
    ):
        result = score_fn(["evt_42"], datetime(2024, 6, 1))

    assert len(result) == 1
    row = result[0]
    assert row["fixture_id"] == "evt_42"
    assert row["market"] == "ou_2.5"
    assert row["selection"] == "over"
    assert 0.0 < row["p_calibrated"] < 1.0
    assert row["p_raw"] == row["p_calibrated"]
    assert row["sigma_p"] == 0.05
    assert row["model_version"] == "xgb_ou25_v1"
    assert len(row["features_hash"]) == 16
