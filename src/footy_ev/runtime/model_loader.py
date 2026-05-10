"""Production model loader for the paper-trading analyst node.

Loads a trained XGBoost O/U 2.5 booster from the warehouse and returns a
`score_fn` closure that the analyst node can call to produce ModelProbability
dicts for a list of fixture_ids.

Key design points:
- Boosters are cached in a module-level dict keyed by run_id so repeated
  graph ticks don't re-deserialize the JSON blob.
- The returned score_fn uses `build_feature_matrix(mode="snapshot")` —
  test-time aggregation, not PIT window functions.
- `sigma_p` is fixed at SIGMA_P_FIXED (conservative constant) because the
  paper trader does not compute fold-specific uncertainty.
- `audit_noise` is set to 0.0 at inference time (the canary column has no
  signal and is ignored by the booster; only its permutation importance is
  audited during training).
- Betfair event IDs do not currently match historical fixture_ids in
  v_fixtures_epl, so build_feature_matrix returns empty rows for live
  fixtures until the Betfair-fixture alignment (Phase 3 step 3) is wired.
  The score_fn returns [] gracefully in that case.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import duckdb
import numpy as np
import xgboost as xgb

from footy_ev.features.assembler import build_feature_matrix

_LOG = logging.getLogger(__name__)

SIGMA_P_FIXED = 0.05

_BOOSTER_CACHE: dict[str, tuple[xgb.Booster, list[str], str]] = {}


class NoProductionModelError(RuntimeError):
    """Raised when no qualifying XGBoost run can be found in the warehouse."""


def detect_production_run_id(con: duckdb.DuckDBPyConnection) -> str:
    """Return the latest completed xgb_ou25_v1 run_id that has persisted fits.

    Strategy: join backtest_runs to xgb_fits by fitting-time window
    (xgb_fits.fitted_at between backtest_runs.started_at and completed_at),
    pick the most-recently-completed qualifying run.

    Raises:
        NoProductionModelError: if no qualifying run is found. Operator must
            run `python run.py canonical` first, or set
            PAPER_TRADER_MODEL_RUN_ID in the environment.
    """
    row = con.execute(
        """
        SELECT br.run_id
        FROM backtest_runs br
        WHERE br.model_version = 'xgb_ou25_v1'
          AND br.status = 'completed'
          AND EXISTS (
              SELECT 1 FROM xgb_fits xf
              WHERE xf.model_version = 'xgb_ou25_v1'
                AND xf.fitted_at >= br.started_at
                AND (br.completed_at IS NULL OR xf.fitted_at <= br.completed_at)
          )
        ORDER BY br.completed_at DESC NULLS LAST
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise NoProductionModelError(
            "No completed xgb_ou25_v1 run with xgb_fits found in the warehouse. "
            "Run `python run.py canonical` first, or pin a run_id via "
            "PAPER_TRADER_MODEL_RUN_ID in .env."
        )
    return str(row[0])


def _load_booster_artifacts(
    con: duckdb.DuckDBPyConnection, run_id: str
) -> tuple[xgb.Booster, list[str], str]:
    """Load (and cache) the latest-fold booster for a given run_id.

    Returns:
        (booster, feature_names, xg_skellam_run_id)

    Raises:
        NoProductionModelError: if no xgb_fits rows exist for this run_id.
    """
    if run_id in _BOOSTER_CACHE:
        return _BOOSTER_CACHE[run_id]

    run_row = con.execute(
        "SELECT started_at, completed_at FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if run_row is None:
        raise NoProductionModelError(
            f"run_id '{run_id}' not found in backtest_runs. "
            "Run `python run.py canonical` to generate a qualifying run."
        )
    started_at, completed_at = run_row

    fit_row = con.execute(
        """
        SELECT booster_json, feature_names, xg_skellam_run_id
        FROM xgb_fits
        WHERE model_version = 'xgb_ou25_v1'
          AND fitted_at >= ?
          AND (? IS NULL OR fitted_at <= ?)
        ORDER BY fitted_at DESC
        LIMIT 1
        """,
        [started_at, completed_at, completed_at],
    ).fetchone()
    if fit_row is None:
        raise NoProductionModelError(
            f"No xgb_fits rows found for run_id '{run_id}' "
            f"(time window {started_at} – {completed_at}). "
            "The XGBoost backtest may have produced no folds."
        )

    booster_json_str, feature_names, xg_skellam_run_id = fit_row
    booster = xgb.Booster()
    booster.load_model(bytearray(booster_json_str.encode("utf-8")))
    _LOG.info(
        "model_loader: loaded booster for run_id=%s xg_skellam_run_id=%s n_features=%d",
        run_id,
        xg_skellam_run_id,
        len(feature_names),
    )
    _BOOSTER_CACHE[run_id] = (booster, feature_names, xg_skellam_run_id)
    return booster, feature_names, xg_skellam_run_id


def load_production_scorer(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
) -> Callable[[list[str], datetime | None], list[dict[str, Any]]]:
    """Return a score_fn closure backed by the production XGBoost booster.

    The closure has the signature expected by analyst_node:
        score_fn(fixture_ids: list[str], as_of: datetime | None) -> list[dict]

    Each returned dict has:
        fixture_id, market, selection, p_calibrated, p_raw, sigma_p,
        model_version, features_hash

    Args:
        con: open DuckDB connection to the warehouse (read access sufficient).
        run_id: backtest run_id whose latest-fold booster to load.

    Returns:
        score_fn closure; the booster is cached after first call.

    Raises:
        NoProductionModelError: if the run or its fits cannot be found.
    """
    booster, feature_names, xg_skellam_run_id = _load_booster_artifacts(con, run_id)

    def score_fn(
        fixture_ids: list[str],
        as_of: datetime | None,
    ) -> list[dict[str, Any]]:
        if not fixture_ids:
            return []
        as_of_ts = as_of or datetime.utcnow()  # noqa: DTZ003 — naive UTC matches DuckDB
        try:
            feat_df = build_feature_matrix(
                con,
                fixture_ids,
                as_of_ts,
                xg_skellam_run_id,
                mode="snapshot",
            )
        except Exception:
            _LOG.exception("model_loader: build_feature_matrix failed; returning []")
            return []

        if feat_df.height == 0:
            _LOG.debug(
                "model_loader: no feature rows returned for %d fixture_ids "
                "(Betfair event IDs not yet aligned to v_fixtures_epl namespace).",
                len(fixture_ids),
            )
            return []

        results: list[dict[str, Any]] = []
        for row in feat_df.iter_rows(named=True):
            fixture_id = str(row["fixture_id"])
            feat_row = {f: row.get(f, np.nan) for f in feature_names}
            feat_row["audit_noise"] = 0.0  # canary; neutral at inference time

            values = np.array(
                [feat_row.get(f, np.nan) for f in feature_names], dtype=float
            ).reshape(1, -1)
            dmatrix = xgb.DMatrix(values, feature_names=feature_names)
            p_over = float(booster.predict(dmatrix)[0])
            p_over = float(np.clip(p_over, 1e-6, 1.0 - 1e-6))

            feat_bytes = ",".join(
                f"{f}:{feat_row.get(f, float('nan')):.6f}" for f in feature_names
            ).encode()
            features_hash = hashlib.sha256(feat_bytes).hexdigest()[:16]

            results.append(
                {
                    "fixture_id": fixture_id,
                    "market": "ou_2.5",
                    "selection": "over",
                    "p_calibrated": p_over,
                    "p_raw": p_over,
                    "sigma_p": SIGMA_P_FIXED,
                    "model_version": "xgb_ou25_v1",
                    "features_hash": features_hash,
                }
            )
        return results

    return score_fn


def clear_booster_cache() -> None:
    """Evict all cached boosters (test helper)."""
    _BOOSTER_CACHE.clear()
