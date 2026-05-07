"""Walk-forward backtest harness.

Per BLUE_MAP §7.1, yields (train_cutoff, test_start, test_end) triples
using a min-seasons warmup followed by stepped expanding-window folds.
Persists fits and predictions to DuckDB (migration 004/006/007 tables).

Boundary convention is half-open:
    training:  kickoff_utc <  train_cutoff
    test:      train_cutoff <= kickoff_utc < test_end
    train_cutoff == test_start (no gap, no overlap)

All datetimes are NAIVE Python datetime objects, interpreted as UTC by
convention. DuckDB TIMESTAMP columns return naive datetimes; this module
keeps them naive throughout.

Model dispatch: `_MODEL_REGISTRY` maps model_version strings to fit/persist/
predict callables. Unknown model_version raises ValueError before the loop.
Promoted-team handling: per skip-and-log policy. The fixture is skipped, no
row is written to model_predictions for it, and the fixture_id is appended to
backtest_runs.notes (truncated to the first 20 to keep the column small).
InsufficientTrainingData from xg_skellam / xgb_ou25 causes the fold to be
skipped with a note; the run continues.

XGBoost path (needs_features=True):
    - PIT feature matrix built via build_feature_matrix(mode="pit") for training.
    - Snapshot feature matrix built via build_feature_matrix(mode="snapshot") for test.
    - audit_noise canary column appended by harness (not by assembler).
    - Permutation importance audit fires per-fold; results persisted to
      xgb_feature_importances.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
import numpy as np
import polars as pl

from footy_ev.eval.feature_audit import permutation_importance_gate
from footy_ev.features.assembler import FEATURE_NAMES, build_feature_matrix
from footy_ev.models.dixon_coles import DCFit, predict_1x2
from footy_ev.models.dixon_coles import fit as dc_fit
from footy_ev.models.xg_skellam import (
    InsufficientTrainingData,
    XGSkellamFit,
    predict_ou25,
)
from footy_ev.models.xg_skellam import (
    fit as xg_fit,
)
from footy_ev.models.xgboost_ou25 import (
    XGBoostOU25Fit,
)
from footy_ev.models.xgboost_ou25 import (
    fit as xgb_fit,
)
from footy_ev.models.xgboost_ou25 import (
    predict_ou25 as xgb_predict_ou25,
)

MODEL_VERSION_DEFAULT = "dc_v1"
DEFAULT_FIXTURES_VIEW = "v_fixtures_epl"


def _now_naive() -> datetime:
    """Return the current UTC time as a naive datetime (matches DuckDB TIMESTAMP)."""
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Predict wrappers — uniform dict interface for the generic harness
# ---------------------------------------------------------------------------


def _dc_predict(fitted: DCFit, home_team_id: str, away_team_id: str) -> dict[str, float]:
    p_h, p_d, p_a = predict_1x2(fitted, home_team_id, away_team_id)
    return {"home": p_h, "draw": p_d, "away": p_a}


def _xg_predict(fitted: XGSkellamFit, home_team_id: str, away_team_id: str) -> dict[str, float]:
    p_over, p_under = predict_ou25(fitted, home_team_id, away_team_id)
    return {"over": p_over, "under": p_under}


def _xgb_predict(fitted: XGBoostOU25Fit, feat_row: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = xgb_predict_ou25(fitted, feat_row)
    return out


# ---------------------------------------------------------------------------
# Fit persistence helpers (model-specific columns)
# ---------------------------------------------------------------------------


def _persist_dc_fit(
    con: duckdb.DuckDBPyConnection,
    league: str,
    dc: DCFit,
    model_version: str,
    **_kwargs: Any,
) -> str:
    fit_id = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO dc_fits (
            fit_id, league, as_of, gamma_home_adv, rho_tau, xi_decay,
            n_train_matches, log_likelihood, optimizer_status, fit_seconds,
            model_version, fitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            fit_id,
            league,
            dc.as_of,
            dc.gamma_home_adv,
            dc.rho_tau,
            dc.xi_decay,
            dc.n_train_matches,
            dc.log_likelihood,
            dc.optimizer_status,
            dc.fit_seconds,
            model_version,
            _now_naive(),
        ],
    )
    rows = [
        (fit_id, team_id, dc.team_attack[team_id], dc.team_defense[team_id])
        for team_id in dc.team_attack
    ]
    con.executemany(
        "INSERT INTO dc_team_params (fit_id, team_id, alpha_attack, beta_defense) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    return fit_id


def _persist_xg_fit(
    con: duckdb.DuckDBPyConnection,
    league: str,
    xg: XGSkellamFit,
    model_version: str,
    **_kwargs: Any,
) -> str:
    fit_id = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO xg_fits (
            fit_id, league, as_of, gamma_home_adv, xi_decay,
            n_train_matches, log_likelihood, optimizer_status, fit_seconds,
            model_version, fitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            fit_id,
            league,
            xg.as_of,
            xg.gamma_home_adv,
            xg.xi_decay,
            xg.n_train_matches,
            xg.log_likelihood,
            xg.optimizer_status,
            xg.fit_seconds,
            model_version,
            _now_naive(),
        ],
    )
    rows = [
        (fit_id, team_id, xg.team_attack[team_id], xg.team_defense[team_id])
        for team_id in xg.team_attack
    ]
    con.executemany(
        "INSERT INTO xg_team_params (fit_id, team_id, alpha_attack, beta_defense) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    return fit_id


def _persist_xgb_fit(
    con: duckdb.DuckDBPyConnection,
    league: str,
    fitted: XGBoostOU25Fit,
    model_version: str,
    **_kwargs: Any,
) -> str:
    fit_id = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO xgb_fits (
            fit_id, league, as_of, model_version, xg_skellam_run_id,
            n_train, n_estimators, max_depth, learning_rate,
            feature_names, booster_json, train_log_loss, fitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            fit_id,
            league,
            fitted.as_of,
            model_version,
            fitted.xg_skellam_run_id,
            fitted.n_train,
            fitted.n_estimators,
            fitted.max_depth,
            fitted.learning_rate,
            fitted.feature_names,
            fitted.booster_json,
            fitted.train_log_loss,
            _now_naive(),
        ],
    )
    return fit_id


def _persist_xgb_importances(
    con: duckdb.DuckDBPyConnection,
    fit_id: str,
    audit_results: dict[str, dict[str, Any]],
    gain_scores: dict[str, float],
) -> None:
    rows = []
    for feat, info in audit_results.items():
        rows.append(
            (
                fit_id,
                feat,
                float(gain_scores.get(feat, 0.0)),
                info.get("permutation_importance"),
                info.get("perm_ci_low"),
                info.get("perm_ci_high"),
                info.get("below_null_baseline"),
            )
        )
    con.executemany(
        """
        INSERT INTO xgb_feature_importances (
            fit_id, feature_name, importance_gain,
            permutation_importance, perm_ci_low, perm_ci_high, below_null_baseline
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

_MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "dc_v1": {
        "market": "1x2",
        "needs_features": False,
        "fit_fn": dc_fit,
        "persist_fit_fn": _persist_dc_fit,
        "predict_fn": _dc_predict,
    },
    "xg_skellam_v1": {
        "market": "ou_2.5",
        "needs_features": False,
        "fit_fn": xg_fit,
        "persist_fit_fn": _persist_xg_fit,
        "predict_fn": _xg_predict,
    },
    "xgb_ou25_v1": {
        "market": "ou_2.5",
        "needs_features": True,
        "fit_fn": xgb_fit,
        "persist_fit_fn": _persist_xgb_fit,
        "predict_fn": _xgb_predict,
    },
}


# ---------------------------------------------------------------------------
# Walk-forward splits
# ---------------------------------------------------------------------------


def walk_forward_splits(
    con: duckdb.DuckDBPyConnection,
    league: str,
    *,
    train_min_seasons: int = 3,
    step_days: int = 7,
    fixtures_view: str = DEFAULT_FIXTURES_VIEW,
) -> Iterator[tuple[datetime, datetime, datetime]]:
    """Yield (train_cutoff, test_start, test_end) triples per BLUE_MAP §7.1.

    First fold's train_cutoff is one microsecond after the last final match
    in the warmup window (seasons[0..train_min_seasons-1]). Subsequent
    folds advance by `step_days`. Stops when current cutoff exceeds the
    most recent final match in the league.

    Args:
        con: open DuckDB connection.
        league: league code (e.g. "EPL").
        train_min_seasons: number of warmup seasons.
        step_days: test window length in days.
        fixtures_view: view name to read fixtures from. Allows overriding
            for unit tests with a synthetic table of the same shape.

    Yields:
        Tuples of (train_cutoff, test_start, test_end), all naive datetimes.
    """
    seasons_df = con.execute(
        f"SELECT DISTINCT season FROM {fixtures_view} WHERE league = ? ORDER BY season",
        [league],
    ).df()
    seasons = seasons_df["season"].tolist()
    if len(seasons) < train_min_seasons + 1:
        return

    warmup_end_season = seasons[train_min_seasons - 1]
    warmup_row = con.execute(
        f"SELECT MAX(kickoff_utc) FROM {fixtures_view} "
        f"WHERE league = ? AND season = ? AND status = 'final'",
        [league, warmup_end_season],
    ).fetchone()
    warmup_end_ts = warmup_row[0] if warmup_row else None
    final_row = con.execute(
        f"SELECT MAX(kickoff_utc) FROM {fixtures_view} WHERE league = ? AND status = 'final'",
        [league],
    ).fetchone()
    final_ts = final_row[0] if final_row else None
    if warmup_end_ts is None or final_ts is None:
        return

    current = warmup_end_ts + timedelta(microseconds=1)
    while current <= final_ts:
        test_start = current
        test_end = current + timedelta(days=step_days)
        yield (current, test_start, test_end)
        current = test_end


# ---------------------------------------------------------------------------
# Generic prediction persistence
# ---------------------------------------------------------------------------


def _features_hash(fit_id: str, home_team_id: str, away_team_id: str) -> str:
    raw = f"{fit_id}|{home_team_id}|{away_team_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def _persist_predictions(
    con: duckdb.DuckDBPyConnection,
    test_matches: pl.DataFrame,
    fitted: Any,
    predict_fn: Callable[..., dict[str, float]],
    market: str,
    fit_id: str,
    run_id: str,
    model_version: str,
    train_cutoff: datetime,
    *,
    feature_matrix: pl.DataFrame | None = None,
) -> tuple[int, list[str]]:
    """Predict for each test match and insert into model_predictions.

    When feature_matrix is provided (XGBoost path), predict_fn receives
    (fitted, feat_row_dict) instead of (fitted, home_team_id, away_team_id).
    Fixtures absent from feature_matrix are skipped.

    Returns:
        (n_inserted_rows, list of skipped fixture_ids).
    """
    features_by_fixture: dict[str, dict[str, float]] = {}
    if feature_matrix is not None:
        for r in feature_matrix.iter_rows(named=True):
            features_by_fixture[r["fixture_id"]] = r

    rows: list[tuple[Any, ...]] = []
    skipped: list[str] = []
    generated_at = _now_naive()
    for r in test_matches.iter_rows(named=True):
        h, a = r["home_team_id"], r["away_team_id"]
        fixture_id = r["fixture_id"]
        try:
            if feature_matrix is not None:
                feat_row = features_by_fixture.get(fixture_id)
                if feat_row is None:
                    skipped.append(fixture_id)
                    continue
                probs = predict_fn(fitted, feat_row)
            else:
                probs = predict_fn(fitted, h, a)
        except KeyError:
            skipped.append(fixture_id)
            continue
        fhash = _features_hash(fit_id, h, a)
        for sel, p in probs.items():
            rows.append(
                (
                    str(uuid.uuid4()),
                    fixture_id,
                    market,
                    sel,
                    p,
                    p,  # p_calibrated == p_raw at backtest time
                    None,  # sigma_p deferred
                    model_version,
                    fhash,
                    train_cutoff,
                    generated_at,
                    run_id,
                )
            )
    if rows:
        con.executemany(
            """
            INSERT INTO model_predictions (
                prediction_id, fixture_id, market, selection, p_raw,
                p_calibrated, sigma_p, model_version, features_hash, as_of,
                generated_at, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows), skipped


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------


def run_backtest(
    con: duckdb.DuckDBPyConnection,
    league: str,
    *,
    train_min_seasons: int = 3,
    step_days: int = 7,
    model_version: str = MODEL_VERSION_DEFAULT,
    xi_decay: float = 0.0019,
    xg_skellam_run_id: str = "",
    fixtures_view: str = DEFAULT_FIXTURES_VIEW,
    feature_subset: list[str] | None = None,
) -> str:
    """Run a full walk-forward backtest, persisting fits and predictions.

    Args:
        con: open DuckDB connection.
        league: league code (e.g. "EPL").
        train_min_seasons: warmup season count.
        step_days: test window length in days.
        model_version: tag stored on fits and predictions; must be in
            _MODEL_REGISTRY or ValueError is raised immediately.
        xi_decay: time-decay rate per day; 0.0 = uniform. Used by DC and
            xg_skellam models; ignored by XGBoost.
        xg_skellam_run_id: run_id of the locked xG-Skellam baseline in
            model_predictions; required when model_version="xgb_ou25_v1".
        fixtures_view: view name. Override for tests.

    Returns:
        run_id (UUID string) of the backtest_runs row.

    Raises:
        ValueError: if model_version is not in _MODEL_REGISTRY.
        Exception: any other exception is captured into
            backtest_runs.status='failed' with the repr in notes, then
            re-raised.
    """
    if model_version not in _MODEL_REGISTRY:
        raise ValueError(
            f"unknown model_version: {model_version!r}. Known: {sorted(_MODEL_REGISTRY)}"
        )

    registry = _MODEL_REGISTRY[model_version]
    market: str = registry["market"]
    needs_features: bool = registry["needs_features"]
    fit_fn = registry["fit_fn"]
    persist_fit_fn = registry["persist_fit_fn"]
    predict_fn = registry["predict_fn"]

    run_id = str(uuid.uuid4())
    started_at = _now_naive()
    con.execute(
        """
        INSERT INTO backtest_runs (
            run_id, model_version, league, train_min_seasons, step_days,
            started_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, 'running')
        """,
        [run_id, model_version, league, train_min_seasons, step_days, started_at],
    )

    n_folds = 0
    n_predictions = 0
    skipped_all: list[str] = []
    insufficient_folds = 0
    try:
        for train_cutoff, test_start, test_end in walk_forward_splits(
            con,
            league,
            train_min_seasons=train_min_seasons,
            step_days=step_days,
            fixtures_view=fixtures_view,
        ):
            train_df = con.execute(
                f"""
                SELECT fixture_id, home_team_id, away_team_id,
                       home_score_ft, away_score_ft, kickoff_utc,
                       home_xg, away_xg
                FROM {fixtures_view}
                WHERE league = ?
                  AND status = 'final'
                  AND kickoff_utc < ?
                  AND home_team_id IS NOT NULL
                  AND away_team_id IS NOT NULL
                """,
                [league, train_cutoff],
            ).pl()
            if train_df.height == 0:
                continue

            try:
                if needs_features:
                    fitted = _fit_xgb_fold(
                        con,
                        train_df,
                        train_cutoff,
                        xg_skellam_run_id,
                        fixtures_view,
                        fold_idx=n_folds,
                        feature_subset=feature_subset,
                    )
                else:
                    fitted = fit_fn(train_df, as_of=train_cutoff, xi_decay=xi_decay)
            except InsufficientTrainingData:
                insufficient_folds += 1
                continue

            fit_id = persist_fit_fn(con, league, fitted, model_version)

            test_df = con.execute(
                f"""
                SELECT fixture_id, home_team_id, away_team_id, kickoff_utc,
                       home_score_ft, away_score_ft
                FROM {fixtures_view}
                WHERE league = ?
                  AND status = 'final'
                  AND kickoff_utc >= ?
                  AND kickoff_utc <  ?
                  AND home_team_id IS NOT NULL
                  AND away_team_id IS NOT NULL
                """,
                [league, test_start, test_end],
            ).pl()

            if needs_features:
                test_feature_matrix = _build_test_features(
                    con,
                    test_df,
                    train_cutoff,
                    xg_skellam_run_id,
                    fixtures_view,
                    fold_idx=n_folds,
                    feature_subset=feature_subset,
                )
                # Permutation audit: needs test labels
                test_labels = _make_ou25_labels(test_df, test_feature_matrix)
                if len(test_labels) > 0:
                    audit_results = permutation_importance_gate(
                        fitted,
                        test_feature_matrix.drop("fixture_id"),
                        test_labels,
                        n_null=100,
                        rng_seed=n_folds,
                    )
                    gain_scores = fitted.classifier.get_booster().get_score(importance_type="gain")
                    _persist_xgb_importances(con, fit_id, audit_results, gain_scores)

                n_inserted, skipped = _persist_predictions(
                    con,
                    test_df,
                    fitted,
                    predict_fn,
                    market,
                    fit_id,
                    run_id,
                    model_version,
                    train_cutoff,
                    feature_matrix=test_feature_matrix,
                )
            else:
                n_inserted, skipped = _persist_predictions(
                    con,
                    test_df,
                    fitted,
                    predict_fn,
                    market,
                    fit_id,
                    run_id,
                    model_version,
                    train_cutoff,
                )

            n_predictions += n_inserted
            skipped_all.extend(skipped)
            n_folds += 1

        notes_parts: list[str] = []
        if skipped_all:
            head = ",".join(skipped_all[:20])
            ellipsis = "..." if len(skipped_all) > 20 else ""
            notes_parts.append(
                f"skipped {len(skipped_all)} predictions for unseen teams: {head}{ellipsis}"
            )
        if insufficient_folds:
            notes_parts.append(
                f"skipped {insufficient_folds} folds due to InsufficientTrainingData"
            )
        notes: str | None = "; ".join(notes_parts) if notes_parts else None

        con.execute(
            """
            UPDATE backtest_runs
            SET completed_at = ?, n_folds = ?, n_predictions = ?,
                status = 'complete', notes = ?
            WHERE run_id = ?
            """,
            [_now_naive(), n_folds, n_predictions, notes, run_id],
        )
    except Exception as exc:
        con.execute(
            """
            UPDATE backtest_runs
            SET completed_at = ?, status = 'failed', notes = ?
            WHERE run_id = ?
            """,
            [_now_naive(), f"error: {exc!r}", run_id],
        )
        raise

    return run_id


# ---------------------------------------------------------------------------
# XGBoost fold helpers
# ---------------------------------------------------------------------------


def _fit_xgb_fold(
    con: duckdb.DuckDBPyConnection,
    train_df: pl.DataFrame,
    train_cutoff: datetime,
    xg_skellam_run_id: str,
    fixtures_view: str,
    fold_idx: int,
    feature_subset: list[str] | None = None,
) -> XGBoostOU25Fit:
    """Build PIT feature matrix + labels and call xgb_fit for one fold."""
    from footy_ev.models.xgboost_ou25 import fit as _xgb_fit

    train_ids = train_df["fixture_id"].to_list()
    feature_df = build_feature_matrix(
        con,
        train_ids,
        train_cutoff,
        xg_skellam_run_id,
        fixtures_view=fixtures_view,
        mode="pit",
        feature_subset=feature_subset,
    )

    # Align features and labels on fixture_id (inner join)
    merged = train_df.join(feature_df, on="fixture_id", how="inner")
    if merged.height == 0:
        from footy_ev.models.xgboost_ou25 import InsufficientTrainingData

        raise InsufficientTrainingData("no training fixtures have features")

    labels = ((merged["home_score_ft"] + merged["away_score_ft"]) > 2.5).cast(pl.Int8).to_numpy()

    feat_cols = feature_df.columns[1:]  # drop fixture_id
    train_noise = np.random.default_rng(fold_idx).uniform(size=len(merged))
    feat_with_noise = merged.select(feat_cols).with_columns(pl.Series("audit_noise", train_noise))

    return _xgb_fit(
        feat_with_noise,
        labels,
        as_of=train_cutoff,
        xg_skellam_run_id=xg_skellam_run_id,
    )


def _build_test_features(
    con: duckdb.DuckDBPyConnection,
    test_df: pl.DataFrame,
    train_cutoff: datetime,
    xg_skellam_run_id: str,
    fixtures_view: str,
    fold_idx: int,
    feature_subset: list[str] | None = None,
) -> pl.DataFrame:
    """Build snapshot feature matrix for test fixtures, appending audit_noise."""
    test_ids = test_df["fixture_id"].to_list()
    cols_for_empty = feature_subset if feature_subset is not None else FEATURE_NAMES
    if not test_ids:
        return pl.DataFrame(
            {"fixture_id": [], **{f: [] for f in cols_for_empty}, "audit_noise": []}
        )

    feature_df = build_feature_matrix(
        con,
        test_ids,
        train_cutoff,
        xg_skellam_run_id,
        fixtures_view=fixtures_view,
        mode="snapshot",
        feature_subset=feature_subset,
    )
    test_noise = np.random.default_rng(fold_idx + 1_000_000).uniform(size=feature_df.height)
    out: pl.DataFrame = feature_df.with_columns(pl.Series("audit_noise", test_noise))
    return out


def _make_ou25_labels(
    test_df: pl.DataFrame,
    test_feature_matrix: pl.DataFrame,
) -> np.ndarray:
    """Return aligned is_over labels for fixtures in test_feature_matrix."""
    if test_feature_matrix.height == 0:
        return np.array([], dtype=np.int8)
    merged = test_df.join(test_feature_matrix.select("fixture_id"), on="fixture_id", how="inner")
    return ((merged["home_score_ft"] + merged["away_score_ft"]) > 2.5).cast(pl.Int8).to_numpy()


if __name__ == "__main__":
    print("walkforward smoke: import OK")
