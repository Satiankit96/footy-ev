"""Unit tests for eval.feature_audit.permutation_importance_gate.

Tests:
  1. A perfectly predictive feature has above_null_baseline (below_null_baseline=False).
  2. audit_noise (pure random) has below_null_baseline=True.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import polars as pl

from footy_ev.eval.feature_audit import permutation_importance_gate
from footy_ev.features.assembler import FEATURE_NAMES
from footy_ev.models.xgboost_ou25 import MIN_XGB_TRAIN_MATCHES, fit

_FEATURE_COLS = FEATURE_NAMES + ["audit_noise"]
_N = MIN_XGB_TRAIN_MATCHES + 100


def _make_fitted_with_signal(rng: np.random.Generator):
    """Fit on data where xg_skellam_p_over is a strong signal for the label."""
    # xg_skellam_p_over ≈ label (with a little noise) — strong signal
    n = _N
    xg_signal = rng.uniform(0.0, 1.0, n)
    labels = (xg_signal + rng.normal(0, 0.1, n) > 0.5).astype(np.int8)

    feature_data: dict[str, list[float]] = {}
    for col in FEATURE_NAMES:
        if col == "xg_skellam_p_over":
            feature_data[col] = xg_signal.tolist()
        else:
            feature_data[col] = rng.uniform(0.0, 1.0, n).tolist()
    feature_data["audit_noise"] = rng.uniform(0.0, 1.0, n).tolist()

    feature_df = pl.DataFrame(feature_data)
    fitted = fit(feature_df, labels, as_of=datetime(2021, 1, 1), xg_skellam_run_id="r")
    return fitted, feature_df, labels


def test_predictive_feature_not_below_null() -> None:
    """xg_skellam_p_over (correlated with label) should not be below null baseline."""
    rng = np.random.default_rng(42)
    fitted, feature_df, labels = _make_fitted_with_signal(rng)

    results = permutation_importance_gate(fitted, feature_df, labels, n_null=50, rng_seed=0)

    # xg_skellam_p_over should be a useful feature — NOT below null
    xg_result = results["xg_skellam_p_over"]
    assert not xg_result["below_null_baseline"], (
        f"xg_skellam_p_over should be above null baseline; "
        f"perm_imp={xg_result['permutation_importance']:.6f}, "
        f"perm_ci_high={xg_result['perm_ci_high']:.6f}"
    )


def test_audit_noise_below_null_baseline() -> None:
    """audit_noise (pure uniform noise) must have below_null_baseline=True."""
    rng = np.random.default_rng(42)
    fitted, feature_df, labels = _make_fitted_with_signal(rng)

    results = permutation_importance_gate(fitted, feature_df, labels, n_null=50, rng_seed=0)

    noise_result = results["audit_noise"]
    assert noise_result["below_null_baseline"], (
        f"audit_noise should be below null baseline; "
        f"perm_imp={noise_result['permutation_importance']:.6f}, "
        f"perm_ci_high={noise_result['perm_ci_high']:.6f}"
    )


def test_all_features_present_in_results() -> None:
    """Results dict must have one entry per feature_name in the fitted model."""
    rng = np.random.default_rng(7)
    fitted, feature_df, labels = _make_fitted_with_signal(rng)

    results = permutation_importance_gate(fitted, feature_df, labels, n_null=10, rng_seed=0)

    assert set(results.keys()) == set(_FEATURE_COLS)


def test_single_class_test_fold_does_not_raise() -> None:
    """Regression: a fold whose test_labels are all 1s (or all 0s) must not crash.

    Realistic on -StepDays 7 EPL runs where one match-week occasionally has
    every fixture go over (or under) 2.5 goals. log_loss requires labels=[0,1]
    explicitly when only one class is present in y_true.
    """
    rng = np.random.default_rng(123)
    fitted, feature_df, _ = _make_fitted_with_signal(rng)

    # Build a small test fold of the same shape but with all-1 labels
    test_n = 20
    test_data: dict[str, list[float]] = {
        col: rng.uniform(0.0, 1.0, test_n).tolist() for col in _FEATURE_COLS
    }
    test_features = pl.DataFrame(test_data)
    all_overs = np.ones(test_n, dtype=np.int8)

    results = permutation_importance_gate(fitted, test_features, all_overs, n_null=10, rng_seed=0)
    assert set(results.keys()) == set(_FEATURE_COLS)

    # Same check for all-0 (all unders)
    all_unders = np.zeros(test_n, dtype=np.int8)
    results_under = permutation_importance_gate(
        fitted, test_features, all_unders, n_null=10, rng_seed=0
    )
    assert set(results_under.keys()) == set(_FEATURE_COLS)
