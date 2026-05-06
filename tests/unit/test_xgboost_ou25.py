"""Unit tests for xgboost_ou25.fit and predict_ou25.

Tests:
  1. fit returns XGBoostOU25Fit with booster_json populated.
  2. predict_ou25 probabilities sum to ~1.0.
  3. InsufficientTrainingData raised when n < MIN_XGB_TRAIN_MATCHES.
  4. feature_names on the returned fit are the input column names.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import polars as pl
import pytest

from footy_ev.features.assembler import FEATURE_NAMES
from footy_ev.models.xgboost_ou25 import (
    MIN_XGB_TRAIN_MATCHES,
    InsufficientTrainingData,
    XGBoostOU25Fit,
    fit,
    predict_ou25,
)

_FEATURE_COLS = FEATURE_NAMES + ["audit_noise"]
_N_TRAIN = MIN_XGB_TRAIN_MATCHES + 50


def _make_feature_df(n: int, rng: np.random.Generator) -> pl.DataFrame:
    data = {col: rng.uniform(0.0, 1.0, n).tolist() for col in _FEATURE_COLS}
    return pl.DataFrame(data)


def _make_labels(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, 2, n).astype(np.int8)


def test_fit_returns_fit_object() -> None:
    """fit() returns XGBoostOU25Fit with non-empty booster_json."""
    rng = np.random.default_rng(0)
    feature_df = _make_feature_df(_N_TRAIN, rng)
    labels = _make_labels(_N_TRAIN, rng)

    fitted = fit(feature_df, labels, as_of=datetime(2021, 1, 1), xg_skellam_run_id="run_x")

    assert isinstance(fitted, XGBoostOU25Fit)
    assert len(fitted.booster_json) > 100, "booster_json should be non-trivial"
    assert fitted.n_train == _N_TRAIN
    assert math.isfinite(fitted.train_log_loss)
    assert fitted.train_log_loss > 0


def test_predict_proba_sums_to_one() -> None:
    """predict_ou25 returns over+under == 1.0 for a random feature row."""
    rng = np.random.default_rng(1)
    feature_df = _make_feature_df(_N_TRAIN, rng)
    labels = _make_labels(_N_TRAIN, rng)
    fitted = fit(feature_df, labels, as_of=datetime(2021, 1, 1), xg_skellam_run_id="run_x")

    feat_row = {col: float(rng.uniform()) for col in _FEATURE_COLS}
    probs = predict_ou25(fitted, feat_row)

    assert set(probs.keys()) == {"over", "under"}
    assert abs(probs["over"] + probs["under"] - 1.0) < 1e-9
    assert 0.0 <= probs["over"] <= 1.0


def test_insufficient_training_data_raises() -> None:
    """fit() raises InsufficientTrainingData when n < MIN_XGB_TRAIN_MATCHES."""
    rng = np.random.default_rng(2)
    small_n = MIN_XGB_TRAIN_MATCHES - 1
    feature_df = _make_feature_df(small_n, rng)
    labels = _make_labels(small_n, rng)

    with pytest.raises(InsufficientTrainingData):
        fit(feature_df, labels, as_of=datetime(2021, 1, 1), xg_skellam_run_id="run_x")


def test_feature_names_match_columns() -> None:
    """fitted.feature_names matches the column order of the input DataFrame."""
    rng = np.random.default_rng(3)
    feature_df = _make_feature_df(_N_TRAIN, rng)
    labels = _make_labels(_N_TRAIN, rng)
    fitted = fit(feature_df, labels, as_of=datetime(2021, 1, 1), xg_skellam_run_id="run_x")

    assert fitted.feature_names == _FEATURE_COLS
