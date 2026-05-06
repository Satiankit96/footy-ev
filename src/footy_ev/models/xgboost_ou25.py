"""XGBoost O/U 2.5 model — Phase 2 step 1.

Fits a binary XGBClassifier (over=1 / under=0) on the 16-feature matrix
(15 SQL features from assembler + audit_noise canary). The audit_noise
canary must always be the last column (index 15) so permutation_importance_gate
can identify it by position via feature_names.

Fixed hyperparameters (grid search deferred to Phase 2 step 2):
    n_estimators=400, max_depth=4, learning_rate=0.05

Walk-forward PIT contract: the caller (walkforward harness) is responsible for
building the feature matrix and labels before calling fit(). This module
contains no SQL; it only wraps XGBClassifier and stores the serialised booster.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
import xgboost as xgb
from sklearn.metrics import log_loss

MIN_XGB_TRAIN_MATCHES = 500

XGB_PARAMS: dict[str, Any] = {
    "n_estimators": 400,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
}


class InsufficientTrainingData(Exception):
    """Raised when fewer than MIN_XGB_TRAIN_MATCHES rows are available."""


@dataclass
class XGBoostOU25Fit:
    """Fitted XGBoost O/U 2.5 model and metadata.

    Attributes:
        as_of: train_cutoff timestamp for this fold.
        xg_skellam_run_id: locked baseline run used for stacked feature.
        feature_names: ordered list of all 16 features (15 SQL + audit_noise).
        classifier: trained XGBClassifier (for fast predict_proba calls).
        booster_json: serialised booster (JSON string; for DB persistence).
        n_train: number of training rows.
        train_log_loss: in-sample log-loss.
        n_estimators: XGB param (stored for xgb_fits table).
        max_depth: XGB param.
        learning_rate: XGB param.
    """

    as_of: datetime
    xg_skellam_run_id: str
    feature_names: list[str]
    classifier: xgb.XGBClassifier
    booster_json: str
    n_train: int
    train_log_loss: float
    n_estimators: int = field(default=XGB_PARAMS["n_estimators"])
    max_depth: int = field(default=XGB_PARAMS["max_depth"])
    learning_rate: float = field(default=XGB_PARAMS["learning_rate"])


def fit(
    feature_df: pl.DataFrame,
    labels: np.ndarray,
    *,
    as_of: datetime,
    xg_skellam_run_id: str,
) -> XGBoostOU25Fit:
    """Fit XGBClassifier on pre-built feature matrix.

    Args:
        feature_df: DataFrame with columns = feature_names (15 SQL + audit_noise).
            Must NOT include fixture_id. Row order must match labels.
        labels: 1-D int array of 0/1 (1 = over 2.5 goals).
        as_of: fold train_cutoff; stored on the returned fit.
        xg_skellam_run_id: stored on the returned fit.

    Returns:
        XGBoostOU25Fit with classifier and serialised booster.

    Raises:
        InsufficientTrainingData: if len(labels) < MIN_XGB_TRAIN_MATCHES.
    """
    n_train = len(labels)
    if n_train < MIN_XGB_TRAIN_MATCHES:
        raise InsufficientTrainingData(
            f"need >= {MIN_XGB_TRAIN_MATCHES} training rows, got {n_train}"
        )

    feature_names = feature_df.columns
    X_pd = pd.DataFrame(feature_df.to_numpy(), columns=feature_names)

    clf = xgb.XGBClassifier(**XGB_PARAMS)
    clf.fit(X_pd, labels)

    train_ll = float(log_loss(labels, clf.predict_proba(X_pd)[:, 1]))
    booster_json = clf.get_booster().save_raw(raw_format="json").decode("utf-8")

    return XGBoostOU25Fit(
        as_of=as_of,
        xg_skellam_run_id=xg_skellam_run_id,
        feature_names=list(feature_names),
        classifier=clf,
        booster_json=booster_json,
        n_train=n_train,
        train_log_loss=train_ll,
        n_estimators=XGB_PARAMS["n_estimators"],
        max_depth=XGB_PARAMS["max_depth"],
        learning_rate=XGB_PARAMS["learning_rate"],
    )


def predict_ou25(fitted: XGBoostOU25Fit, feat_row: dict[str, float]) -> dict[str, float]:
    """Predict O/U 2.5 probabilities for a single fixture.

    Args:
        fitted: trained XGBoostOU25Fit.
        feat_row: dict mapping feature name -> value; must contain all
            columns in fitted.feature_names (NaN is allowed for missing).

    Returns:
        {"over": p_over, "under": p_under} summing to 1.0.
    """
    X = np.array([[feat_row.get(f, np.nan) for f in fitted.feature_names]], dtype=float)
    X_pd = pd.DataFrame(X, columns=fitted.feature_names)
    p_over = float(fitted.classifier.predict_proba(X_pd)[0, 1])
    return {"over": p_over, "under": 1.0 - p_over}


if __name__ == "__main__":
    print(
        f"xgboost_ou25 smoke: MIN_XGB_TRAIN_MATCHES={MIN_XGB_TRAIN_MATCHES}, "
        f"XGB_PARAMS={XGB_PARAMS}"
    )
