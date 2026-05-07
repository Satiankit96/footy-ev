"""Permutation importance gate for XGBoost fold audit (BLUE_MAP §7.3).

Each fold fires one audit:
  1. Compute baseline log-loss on test features.
  2. Build a null CI by permuting the audit_noise canary n_null=100 times
     and recording log-loss drops.
  3. For each feature: permute once, compute log-loss drop (permutation
     importance). Flag below_null_baseline=True if importance <= perm_ci_high.

audit_noise must be the last column in the feature matrix (convention set by
the walkforward harness). A well-functioning audit finds audit_noise with
below_null_baseline=True; if it's flagged as important, there is a data-leakage
or implementation bug.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import log_loss

from footy_ev.models.xgboost_ou25 import XGBoostOU25Fit


def permutation_importance_gate(
    fitted: XGBoostOU25Fit,
    test_features: pl.DataFrame,
    test_labels: np.ndarray,
    *,
    n_null: int = 100,
    rng_seed: int = 0,
) -> dict[str, dict[str, Any]]:
    """Compute per-feature permutation importances vs audit_noise null CI.

    Args:
        fitted: trained XGBoostOU25Fit with feature_names (including audit_noise).
        test_features: DataFrame with columns matching fitted.feature_names.
            Rows must align with test_labels.
        test_labels: 1-D array of 0/1 (1 = over 2.5 goals).
        n_null: number of audit_noise permutations to build the null CI.
        rng_seed: RNG seed for reproducibility.

    Returns:
        Dict mapping feature_name -> {
            "permutation_importance": float,   # log-loss increase when permuted
            "perm_ci_low": float,              # 5th pct of null distribution
            "perm_ci_high": float,             # 95th pct of null distribution
            "below_null_baseline": bool,       # True if importance <= perm_ci_high
        }
    """
    rng = np.random.default_rng(rng_seed)
    feature_names = fitted.feature_names
    clf = fitted.classifier

    X = test_features.select(feature_names).to_numpy().astype(float)
    len(X)

    y_pred_base = clf.predict_proba(pd.DataFrame(X, columns=feature_names))[:, 1]
    baseline_ll = log_loss(test_labels, y_pred_base, labels=[0, 1])

    audit_idx = feature_names.index("audit_noise")

    # Build null CI by permuting audit_noise n_null times
    null_importances: list[float] = []
    for _ in range(n_null):
        X_p = X.copy()
        X_p[:, audit_idx] = rng.permutation(X_p[:, audit_idx])
        ll_p = log_loss(
            test_labels,
            clf.predict_proba(pd.DataFrame(X_p, columns=feature_names))[:, 1],
            labels=[0, 1],
        )
        null_importances.append(ll_p - baseline_ll)

    null_arr = np.array(null_importances)
    perm_ci_low = float(np.percentile(null_arr, 5))
    perm_ci_high = float(np.percentile(null_arr, 95))

    results: dict[str, dict[str, Any]] = {}
    for i, feat in enumerate(feature_names):
        X_p = X.copy()
        X_p[:, i] = rng.permutation(X_p[:, i])
        ll_p = log_loss(
            test_labels,
            clf.predict_proba(pd.DataFrame(X_p, columns=feature_names))[:, 1],
            labels=[0, 1],
        )
        perm_imp = ll_p - baseline_ll
        results[feat] = {
            "permutation_importance": perm_imp,
            "perm_ci_low": perm_ci_low,
            "perm_ci_high": perm_ci_high,
            "below_null_baseline": bool(perm_imp <= perm_ci_high),
        }

    return results


if __name__ == "__main__":
    print("feature_audit smoke: import OK")
