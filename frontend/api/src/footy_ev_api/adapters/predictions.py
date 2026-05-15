"""Predictions adapter — read/run against model_predictions via DuckDB."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from footy_ev_api.errors import AppError
from footy_ev_api.jobs.manager import Job
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)

# Static feature documentation — sourced from features/assembler.py docstrings.
# Choice rationale: static mapping avoids runtime coupling to feature view SQL;
# feature semantics are stable across model versions since FEATURE_NAMES is
# a versioned constant in the assembler.
FEATURE_DOCS: dict[str, str] = {
    "home_xg_for_5": "Home team average xG scored per match, last 5 matches",
    "away_xg_for_5": "Away team average xG scored per match, last 5 matches",
    "home_xg_against_5": "Home team average xG conceded per match, last 5 matches",
    "away_xg_against_5": "Away team average xG conceded per match, last 5 matches",
    "home_goals_for_5": "Home team average goals scored per match, last 5 matches",
    "away_goals_for_5": "Away team average goals scored per match, last 5 matches",
    "home_goals_against_5": "Home team average goals conceded per match, last 5 matches",
    "away_goals_against_5": "Away team average goals conceded per match, last 5 matches",
    "home_win_rate_10": "Home team win rate (1=win, 0=other), last 10 matches",
    "away_win_rate_10": "Away team win rate, last 10 matches",
    "home_draw_rate_10": "Home team draw rate, last 10 matches",
    "away_draw_rate_10": "Away team draw rate, last 10 matches",
    "home_ppg_10": "Home team points-per-game on 0–1 scale (1.0 = 3 pts/match), last 10 matches",
    "away_ppg_10": "Away team points-per-game on 0–1 scale, last 10 matches",
    "xg_skellam_p_over": "xG-Skellam baseline probability of over 2.5 goals for this fixture",
}


def _db_path() -> Path:
    return Path(Settings().warehouse_path)


def _connect(*, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    db = _db_path()
    if not db.exists():
        raise AppError("WAREHOUSE_NOT_FOUND", f"Warehouse not found at {db}", 503)
    con = duckdb.connect(str(db), read_only=read_only)
    from footy_ev.db import apply_migrations, apply_views

    apply_migrations(con)
    apply_views(con)
    return con


def list_predictions(
    *,
    fixture_id: str | None = None,
    model_version: str | None = None,
    market: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Paginated predictions list with composable AND filters."""
    con = _connect()
    try:
        where_parts: list[str] = []
        params: list[Any] = []

        if fixture_id:
            where_parts.append("fixture_id = ?")
            params.append(fixture_id)
        if model_version:
            where_parts.append("model_version = ?")
            params.append(model_version)
        if market:
            where_parts.append("market = ?")
            params.append(market)
        if date_from:
            where_parts.append("as_of >= CAST(? AS TIMESTAMP)")
            params.append(date_from)
        if date_to:
            where_parts.append("as_of <= CAST(? AS TIMESTAMP)")
            params.append(date_to)

        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        count_row = con.execute(
            f"SELECT COUNT(*) FROM model_predictions {where}",  # noqa: S608
            params,
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        rows = con.execute(
            f"SELECT prediction_id, fixture_id, market, selection, "  # noqa: S608
            f"p_raw, p_calibrated, sigma_p, model_version, features_hash, "
            f"as_of, generated_at, run_id "
            f"FROM model_predictions {where} "
            "ORDER BY as_of DESC, prediction_id "
            "LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        predictions = [_row_to_dict(r) for r in rows]
        return {"predictions": predictions, "total": total}
    except duckdb.CatalogException:
        return {"predictions": [], "total": 0}
    finally:
        con.close()


def get_prediction(prediction_id: str) -> dict[str, Any] | None:
    """Single prediction by ID."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT prediction_id, fixture_id, market, selection, "
            "p_raw, p_calibrated, sigma_p, model_version, features_hash, "
            "as_of, generated_at, run_id "
            "FROM model_predictions WHERE prediction_id = ?",
            [prediction_id],
        ).fetchone()
        return _row_to_dict(row) if row else None
    except duckdb.CatalogException:
        return None
    finally:
        con.close()


def get_prediction_features(prediction_id: str) -> dict[str, Any] | None:
    """Reconstruct the feature vector that produced a prediction.

    Calls build_feature_matrix with mode='snapshot' and the stored as_of
    timestamp, then enriches each feature with its documentation string.
    The features_hash stored in the prediction serves as a checksum.
    """
    con = _connect()
    try:
        row = con.execute(
            "SELECT fixture_id, as_of, run_id, features_hash, model_version "
            "FROM model_predictions WHERE prediction_id = ?",
            [prediction_id],
        ).fetchone()
        if not row:
            return None

        fixture_id, as_of_ts, run_id, stored_hash, model_version = row

        xg_skellam_run_id: str | None = None
        if run_id:
            try:
                fit_row = con.execute(
                    "SELECT xg_skellam_run_id FROM xgb_fits "
                    "WHERE model_version = 'xgb_ou25_v1' "
                    "ORDER BY fitted_at DESC LIMIT 1",
                ).fetchone()
                if fit_row:
                    xg_skellam_run_id = str(fit_row[0])
            except duckdb.CatalogException:
                pass

        if xg_skellam_run_id is None:
            xg_skellam_run_id = run_id or ""

        try:
            from footy_ev.features.assembler import FEATURE_NAMES, build_feature_matrix

            feat_df = build_feature_matrix(
                con,
                [fixture_id],
                as_of_ts,
                xg_skellam_run_id,
                mode="snapshot",
            )
        except Exception as exc:
            _LOG.warning("Could not reconstruct features for %s: %s", prediction_id, exc)
            return {
                "prediction_id": prediction_id,
                "fixture_id": fixture_id,
                "features_hash": stored_hash,
                "features": [],
                "error": f"Feature reconstruction unavailable: {exc}",
            }

        features: list[dict[str, Any]] = []
        if feat_df.height > 0:
            row_data = feat_df.row(0, named=True)
            for name in FEATURE_NAMES:
                val = row_data.get(name)
                features.append(
                    {
                        "name": name,
                        "value": float(val) if val is not None else None,
                        "description": FEATURE_DOCS.get(name, name),
                    }
                )

        return {
            "prediction_id": prediction_id,
            "fixture_id": fixture_id,
            "features_hash": stored_hash,
            "features": features,
        }
    except duckdb.CatalogException:
        return None
    finally:
        con.close()


def run_predictions(
    job: Job,
    broadcast: Callable[[dict[str, Any]], None],
    *,
    fixture_ids: list[str] | None = None,
) -> None:
    """Score fixtures in-process and write results to model_predictions.

    Calls load_production_scorer() from the model_loader, runs score_fn
    in-process (no subprocess), then upserts rows into model_predictions.
    """

    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _emit(step: str, message: str, percent: int = 0) -> None:
        event = {
            "type": "progress",
            "timestamp": _now_iso(),
            "payload": {
                "job_id": job.job_id,
                "step": step,
                "message": message,
                "percent": percent,
            },
        }
        job.progress.append(event)
        broadcast(event)

    try:
        con = _connect(read_only=False)
    except AppError:
        raise

    try:
        as_of = datetime.now(tz=UTC)
        run_id = f"api_run_{uuid.uuid4().hex[:12]}"

        _emit("init", "Loading production scorer", 5)
        try:
            from footy_ev.runtime.model_loader import (
                detect_production_run_id,
                load_production_scorer,
            )

            model_run_id = detect_production_run_id(con)
            score_fn = load_production_scorer(con, model_run_id)
        except Exception as exc:
            raise AppError(
                "NO_PRODUCTION_MODEL",
                f"No production model available: {exc}. "
                "Run `python run.py canonical` to train the XGBoost model first.",
                503,
            ) from exc

        target_ids: list[str] = list(fixture_ids or [])
        if not target_ids:
            _emit("discover", "Discovering scheduled fixtures with active aliases", 10)
            try:
                rows = con.execute(
                    "SELECT DISTINCT f.fixture_id "
                    "FROM v_fixtures_epl f "
                    "JOIN kalshi_event_aliases kea ON kea.fixture_id = f.fixture_id "
                    "WHERE f.status = 'scheduled' "
                    "  AND COALESCE(kea.status, 'active') = 'active' "
                    "  AND f.kickoff_utc <= now() + INTERVAL 14 DAYS "
                    "ORDER BY f.fixture_id",
                ).fetchall()
                target_ids = [r[0] for r in rows]
            except duckdb.CatalogException:
                target_ids = []

        if not target_ids:
            result = {"scored_count": 0, "written_count": 0, "run_id": run_id}
            job.progress.append({"type": "result", "payload": result})
            broadcast(
                {
                    "type": "completed",
                    "timestamp": _now_iso(),
                    "payload": {"job_id": job.job_id, **result},
                }
            )
            return

        _emit("score", f"Scoring {len(target_ids)} fixture(s)", 30)
        raw: list[dict[str, Any]] = score_fn(target_ids, as_of)

        _emit("write", f"Writing {len(raw)} prediction row(s)", 70)
        written = 0
        generated_at = datetime.now(tz=UTC)
        for r in raw:
            pid = hashlib.sha256(
                f"{run_id}|{r['fixture_id']}|{r['market']}|{r['selection']}".encode()
            ).hexdigest()[:32]
            try:
                con.execute(
                    """
                    INSERT INTO model_predictions
                        (prediction_id, fixture_id, market, selection,
                         p_raw, p_calibrated, sigma_p, model_version,
                         features_hash, as_of, generated_at, run_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (prediction_id) DO UPDATE SET
                        p_raw = excluded.p_raw,
                        p_calibrated = excluded.p_calibrated,
                        sigma_p = excluded.sigma_p,
                        features_hash = excluded.features_hash,
                        generated_at = excluded.generated_at
                    """,
                    [
                        pid,
                        r["fixture_id"],
                        r["market"],
                        r["selection"],
                        r.get("p_raw", r["p_calibrated"]),
                        r["p_calibrated"],
                        r.get("sigma_p"),
                        r.get("model_version", "xgb_ou25_v1"),
                        r.get("features_hash", ""),
                        as_of,
                        generated_at,
                        run_id,
                    ],
                )
                written += 1
            except Exception as exc:
                _LOG.warning("Failed to write prediction %s: %s", pid, exc)

        result = {
            "scored_count": len(raw),
            "written_count": written,
            "run_id": run_id,
            "fixture_count": len(target_ids),
        }
        job.progress.append({"type": "result", "payload": result})
        broadcast(
            {
                "type": "completed",
                "timestamp": _now_iso(),
                "payload": {"job_id": job.job_id, **result},
            }
        )

    except AppError:
        raise
    except Exception as exc:
        broadcast(
            {
                "type": "failed",
                "timestamp": _now_iso(),
                "payload": {"job_id": job.job_id, "error": str(exc)},
            }
        )
        raise
    finally:
        con.close()


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "prediction_id": row[0],
        "fixture_id": row[1],
        "market": row[2],
        "selection": row[3],
        "p_raw": row[4],
        "p_calibrated": row[5],
        "sigma_p": row[6],
        "model_version": row[7],
        "features_hash": row[8],
        "as_of": row[9].isoformat() if row[9] else None,
        "generated_at": row[10].isoformat() if row[10] else None,
        "run_id": row[11],
    }
