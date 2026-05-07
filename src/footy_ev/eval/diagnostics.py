"""Phase 2 step 2 diagnostics for XGBoost O/U 2.5 (xgb_ou25_v1).

Two diagnostics intended to be run against an existing completed XGBoost run:

  feature_sanity(con, xgb_run_id)
      Replays the snapshot feature assembler over every (as_of, fixture_id)
      pair predicted by the XGBoost run and aggregates the distribution of
      `xg_skellam_p_over`. If most rows hit the COALESCE(..., 0.5) default,
      the PIT JOIN to model_predictions is broken and the stacked feature
      was never actually delivered.

  shap_importance(con, xgb_run_id, fold_idx=-1)
      Rehydrates the most-recent (or selected) fold's booster from
      xgb_fits.booster_json and computes mean(|SHAP|) per feature on that
      fold's snapshot test feature matrix. Captures correlated-substitution
      effects that permutation importance can hide when features collinear
      with xg_skellam_p_over absorb the gradient.

Neither diagnostic mutates state. Both write nothing to the warehouse.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import polars as pl
import xgboost as xgb

from footy_ev.features.assembler import build_feature_matrix

# ---------------------------------------------------------------------------
# Diag 1 — feature matrix sanity audit
# ---------------------------------------------------------------------------


def feature_sanity(
    con: duckdb.DuckDBPyConnection,
    xgb_run_id: str,
    *,
    default_value: float = 0.5,
    fixtures_view: str = "v_fixtures_epl",
) -> dict[str, Any]:
    """Aggregate the distribution of `xg_skellam_p_over` across an XGBoost run.

    Replays the snapshot feature assembler for each (as_of, fixture_id) tuple
    that the XGBoost run produced predictions for. The result tells us
    whether the stacked feature was actually delivered (well-distributed
    values across [0, 1]) or silently defaulted to 0.5 (broken JOIN).

    Args:
        con: open DuckDB connection.
        xgb_run_id: completed `xgb_ou25_v1` run_id.
        default_value: COALESCE default for the stacked feature (assembler
            uses 0.5; rows hitting this are JOIN misses).
        fixtures_view: fixtures view name; override for tests.

    Returns:
        Dict with aggregate stats:
          xgb_run_id, xg_skellam_run_id, n_folds, n_rows,
          n_at_default, frac_at_default, min, max, mean, stddev, median,
          per_fold (list of {as_of, n_rows, n_at_default, mean}).
    """
    skellam_row = con.execute(
        """
        SELECT DISTINCT xf.xg_skellam_run_id
        FROM xgb_fits xf, backtest_runs br
        WHERE br.run_id = ?
          AND xf.model_version = 'xgb_ou25_v1'
          AND xf.fitted_at >= br.started_at
          AND xf.fitted_at <= COALESCE(br.completed_at, xf.fitted_at)
        """,
        [xgb_run_id],
    ).fetchall()
    if len(skellam_row) != 1 or not skellam_row[0][0]:
        raise ValueError(
            f"could not resolve unique xg_skellam_run_id for xgb run "
            f"{xgb_run_id}; got {skellam_row}"
        )
    skellam_run_id = skellam_row[0][0]

    asof_fixtures = con.execute(
        """
        SELECT as_of, fixture_id
        FROM model_predictions
        WHERE run_id = ? AND market = 'ou_2.5' AND selection = 'over'
        ORDER BY as_of, fixture_id
        """,
        [xgb_run_id],
    ).fetchall()
    if not asof_fixtures:
        raise ValueError(f"no predictions for run_id={xgb_run_id}")

    asof_to_fixtures: dict[Any, list[str]] = {}
    for asof, fid in asof_fixtures:
        asof_to_fixtures.setdefault(asof, []).append(fid)

    per_fold: list[dict[str, Any]] = []
    all_values: list[float] = []
    for asof in sorted(asof_to_fixtures.keys()):
        fids = asof_to_fixtures[asof]
        fm = build_feature_matrix(
            con,
            fids,
            asof,
            skellam_run_id,
            fixtures_view=fixtures_view,
            mode="snapshot",
            feature_subset=["xg_skellam_p_over"],
        )
        vals = fm["xg_skellam_p_over"].to_list()
        all_values.extend(vals)
        if vals:
            n_default = sum(1 for v in vals if v == default_value)
            per_fold.append(
                {
                    "as_of": asof,
                    "n_rows": len(vals),
                    "n_at_default": n_default,
                    "mean": float(np.mean(vals)),
                }
            )

    arr = np.array(all_values, dtype=float)
    n = int(arr.size)
    n_default = int(np.sum(arr == default_value)) if n else 0
    return {
        "xgb_run_id": xgb_run_id,
        "xg_skellam_run_id": skellam_run_id,
        "n_folds": len(per_fold),
        "n_rows": n,
        "n_at_default": n_default,
        "frac_at_default": (n_default / n) if n else 0.0,
        "min": float(arr.min()) if n else None,
        "max": float(arr.max()) if n else None,
        "mean": float(arr.mean()) if n else None,
        "stddev": float(arr.std(ddof=1)) if n > 1 else None,
        "median": float(np.median(arr)) if n else None,
        "per_fold": per_fold,
    }


# ---------------------------------------------------------------------------
# Diag 3 — SHAP importance on a rehydrated fold
# ---------------------------------------------------------------------------


def _rehydrate_booster(booster_json: str) -> xgb.Booster:
    """Load a booster from the JSON string persisted in xgb_fits.booster_json."""
    booster = xgb.Booster()
    booster.load_model(bytearray(booster_json, "utf-8"))
    return booster


def shap_importance(
    con: duckdb.DuckDBPyConnection,
    xgb_run_id: str,
    *,
    fold_idx: int = -1,
    fixtures_view: str = "v_fixtures_epl",
) -> pl.DataFrame:
    """Compute mean(|SHAP|) per feature on one fold's test set.

    Picks the `fold_idx`-th fit ordered by `as_of` ascending (default -1 =
    most-recent fold), rehydrates its booster from xgb_fits.booster_json,
    rebuilds the snapshot feature matrix on that fold's test fixtures, and
    runs `shap.TreeExplainer.shap_values`.

    Args:
        con: open DuckDB connection.
        xgb_run_id: completed `xgb_ou25_v1` run_id.
        fold_idx: index into the fold list ordered by as_of ascending.
            -1 selects the most recent fold (default).
        fixtures_view: fixtures view name; override for tests.

    Returns:
        Polars DataFrame with columns [feature_name, mean_abs_shap], sorted
        by mean_abs_shap descending.
    """
    import shap  # local import to keep module import cheap

    run_meta = con.execute(
        "SELECT step_days, league, started_at, completed_at FROM backtest_runs WHERE run_id = ?",
        [xgb_run_id],
    ).fetchone()
    if not run_meta:
        raise ValueError(f"no backtest_runs row for run_id={xgb_run_id}")
    step_days, league, started_at, completed_at = run_meta
    if completed_at is None:
        raise ValueError(f"run {xgb_run_id} has no completed_at; not finished?")

    fits = con.execute(
        """
        SELECT fit_id, as_of, xg_skellam_run_id, feature_names, booster_json
        FROM xgb_fits
        WHERE fitted_at >= ? AND fitted_at <= ? AND model_version = 'xgb_ou25_v1'
        ORDER BY as_of ASC
        """,
        [started_at, completed_at],
    ).fetchall()
    if not fits:
        raise ValueError(f"no xgb_fits rows for run_id={xgb_run_id}")

    if not -len(fits) <= fold_idx < len(fits):
        raise IndexError(f"fold_idx={fold_idx} out of range; run has {len(fits)} folds")
    fit_id, as_of, skellam_run_id, feature_names, booster_json = fits[fold_idx]

    test_end = as_of + timedelta(days=step_days)
    test_ids = [
        r[0]
        for r in con.execute(
            f"""
            SELECT fixture_id FROM {fixtures_view}
            WHERE league = ? AND status = 'final'
              AND kickoff_utc >= ? AND kickoff_utc < ?
              AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL
            ORDER BY kickoff_utc
            """,
            [league, as_of, test_end],
        ).fetchall()
    ]
    if not test_ids:
        raise ValueError(f"no test fixtures for fold as_of={as_of}")

    sql_features = [n for n in feature_names if n != "audit_noise"]
    fm = build_feature_matrix(
        con,
        test_ids,
        as_of,
        skellam_run_id,
        fixtures_view=fixtures_view,
        mode="snapshot",
        feature_subset=sql_features,
    )
    if "audit_noise" in feature_names:
        rng = np.random.default_rng(2_000_000)
        fm = fm.with_columns(pl.Series("audit_noise", rng.uniform(size=fm.height)))

    X_pd = pd.DataFrame(
        fm.select(feature_names).to_numpy(),
        columns=feature_names,
    )

    booster = _rehydrate_booster(booster_json)
    explainer = shap.TreeExplainer(booster)
    sv = explainer.shap_values(X_pd)
    mean_abs = np.mean(np.abs(sv), axis=0)

    return pl.DataFrame(
        {
            "feature_name": feature_names,
            "mean_abs_shap": mean_abs.tolist(),
        }
    ).sort("mean_abs_shap", descending=True)


if __name__ == "__main__":
    print("diagnostics smoke: import OK")
