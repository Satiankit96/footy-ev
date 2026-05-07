"""Walk-forward isotonic calibration for model predictions (any market).

Per project convention (Phase 1 step 2 / step 3):
  - For each fold k (sorted by as_of), per (market, selection) pair present
    in the run's model_predictions:
      train  := all (p_raw, is_winner) pairs from folds with as_of < k
      test   := this fold's predictions for that (market, selection)
      if len(train) >= MIN_TRAIN_N: fit IsotonicRegression on train, apply to test
      else: identity passthrough (p_calibrated = p_raw)
  - The per-fold calibrated values are returned in a {prediction_id ->
    p_calibrated} mapping; clv.py consumes this to write
    clv_evaluations.p_calibrated.
  - The FINAL end-of-run isotonic fit per (market, selection) is persisted
    to calibration_fits for inspection and reuse.

`model_predictions.p_calibrated` is intentionally NOT updated in place —
that column was set equal to p_raw in step 1 and remains the canonical raw
output. All calibrated values live in clv_evaluations.p_calibrated.

is_winner handles both 1x2 (derived from result_ft) and ou_2.5 (derived
from home_score_ft + away_score_ft).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import duckdb
import numpy as np
import polars as pl
from sklearn.isotonic import IsotonicRegression

MIN_TRAIN_N = 500  # per-(market,selection) minimum prior predictions before fitting
SELECTIONS = ("home", "draw", "away")  # kept for callers that use it as a 1x2 sentinel


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _is_winner_sql(
    selection_col: str = "mp.selection",
    result_col: str = "f.result_ft",
    home_score_col: str = "f.home_score_ft",
    away_score_col: str = "f.away_score_ft",
) -> str:
    return (
        f"CASE "
        f"WHEN {selection_col} = 'home'  AND {result_col} = 'H' THEN TRUE "
        f"WHEN {selection_col} = 'draw'  AND {result_col} = 'D' THEN TRUE "
        f"WHEN {selection_col} = 'away'  AND {result_col} = 'A' THEN TRUE "
        f"WHEN {selection_col} = 'over'  "
        f"     AND ({home_score_col} + {away_score_col}) > 2 THEN TRUE "
        f"WHEN {selection_col} = 'under' "
        f"     AND ({home_score_col} + {away_score_col}) <= 2 THEN TRUE "
        f"ELSE FALSE END"
    )


def fit_isotonic_walk_forward(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    *,
    fixtures_view: str = "v_fixtures_epl",
    min_train_n: int = MIN_TRAIN_N,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """Walk-forward isotonic over a backtest run's predictions.

    Discovers distinct (market, selection) pairs from model_predictions and
    calibrates each independently. Supports 1x2 (home/draw/away) and
    ou_2.5 (over/under) out of the box via _is_winner_sql.

    Args:
        con: open DuckDB connection (read + write).
        run_id: identifier in backtest_runs.
        fixtures_view: source of result_ft / scores to derive is_winner.
        min_train_n: per-(market,selection) threshold for fitting.

    Returns:
        (calibrated_probs, per_selection_state)
            calibrated_probs: dict[prediction_id -> p_calibrated]. Includes
                every prediction (folds with insufficient train get
                passthrough = p_raw).
            per_selection_state: dict[selection -> {iso, n_train, n_test,
                brier_raw, brier_calibrated, market}]. iso is the FINAL
                end-of-run IsotonicRegressor fit on the full (p_raw,
                is_winner) set per selection. Within a run, selection names
                are unique across markets.
    """
    # Discover which (market, selection) pairs exist for this run.
    ms_rows = con.execute(
        "SELECT DISTINCT market, selection FROM model_predictions WHERE run_id = ?",
        [run_id],
    ).fetchall()
    if not ms_rows:
        return {}, {}

    distinct_sels = [r[1] for r in ms_rows]
    market_by_sel = {r[1]: r[0] for r in ms_rows}

    iw_sql = _is_winner_sql()
    df = con.execute(
        f"""
        SELECT mp.prediction_id, mp.fixture_id, mp.selection, mp.p_raw,
               mp.as_of,
               {iw_sql} AS is_winner
        FROM model_predictions mp
        JOIN {fixtures_view} f ON f.fixture_id = mp.fixture_id
        WHERE mp.run_id = ? AND f.result_ft IS NOT NULL
        ORDER BY mp.as_of, mp.selection, mp.prediction_id
        """,
        [run_id],
    ).pl()

    calibrated: dict[str, float] = {}
    if df.height == 0:
        return calibrated, {}

    distinct_as_of = sorted(set(df["as_of"].to_list()))

    accum: dict[str, dict[str, list[float]]] = {
        sel: {"p_raw_test": [], "p_cal_test": [], "is_win_test": []} for sel in distinct_sels
    }

    for current_as_of in distinct_as_of:
        for sel in distinct_sels:
            prior = df.filter((pl.col("as_of") < current_as_of) & (pl.col("selection") == sel))
            current = df.filter((pl.col("as_of") == current_as_of) & (pl.col("selection") == sel))
            if current.height == 0:
                continue
            cur_p_raw = current["p_raw"].to_numpy()
            cur_pred_ids = current["prediction_id"].to_list()
            cur_is_win = current["is_winner"].to_numpy().astype(bool)

            if prior.height >= min_train_n:
                iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
                iso.fit(
                    prior["p_raw"].to_numpy(),
                    prior["is_winner"].to_numpy().astype(float),
                )
                cur_p_cal = iso.transform(cur_p_raw)
            else:
                cur_p_cal = cur_p_raw.copy()

            for pred_id, p_c in zip(cur_pred_ids, cur_p_cal, strict=False):
                calibrated[pred_id] = float(p_c)

            accum[sel]["p_raw_test"].extend(cur_p_raw.tolist())
            accum[sel]["p_cal_test"].extend(cur_p_cal.tolist())
            accum[sel]["is_win_test"].extend(cur_is_win.tolist())

    state: dict[str, dict[str, Any]] = {}
    for sel in distinct_sels:
        a = accum[sel]
        if not a["p_raw_test"]:
            continue
        p_raw_arr = np.array(a["p_raw_test"])
        p_cal_arr = np.array(a["p_cal_test"])
        is_win_arr = np.array(a["is_win_test"], dtype=bool)
        y_float = is_win_arr.astype(float)
        brier_raw = float(np.mean((p_raw_arr - y_float) ** 2))
        brier_cal = float(np.mean((p_cal_arr - y_float) ** 2))
        iso_final = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
        iso_final.fit(p_raw_arr, y_float)
        state[sel] = {
            "iso": iso_final,
            "n_train": int(len(p_raw_arr)),
            "n_test": int(len(p_cal_arr)),
            "brier_raw": brier_raw,
            "brier_calibrated": brier_cal,
            "market": market_by_sel[sel],
        }
    return calibrated, state


def persist_calibration_fits(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    state: dict[str, dict[str, Any]],
) -> None:
    """Write final per-(market, selection) isotonic params + Brier to calibration_fits."""
    if not state:
        return
    rows = []
    fitted_at = _now_naive()
    for sel, s in state.items():
        iso = s["iso"]
        market = s.get("market", "1x2")
        x_thresh = [float(v) for v in iso.X_thresholds_]
        y_thresh = [float(v) for v in iso.y_thresholds_]
        rows.append(
            (
                str(uuid.uuid4()),
                run_id,
                market,
                sel,
                x_thresh,
                y_thresh,
                s["n_train"],
                s["n_test"],
                s["brier_raw"],
                s["brier_calibrated"],
                fitted_at,
            )
        )
    con.executemany(
        """
        INSERT INTO calibration_fits (
            fit_id, run_id, market, selection, iso_x, iso_y, n_train, n_test,
            brier_raw, brier_calibrated, fitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
