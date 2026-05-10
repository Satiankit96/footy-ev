"""Parameterized read-only DuckDB queries for the Streamlit dashboard.

All public functions:
  - Accept a duckdb.DuckDBPyConnection opened in read_only=True mode.
  - Return polars DataFrames (or plain dicts for single-row summaries).
  - Never mutate state.
  - Use ? parameterization — no f-string SQL for data values.
"""

from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import polars as pl

# ---------------------------------------------------------------------------
# Overview page
# ---------------------------------------------------------------------------


def runs_list(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """All backtest_runs sorted newest first."""
    return con.execute(
        """
        SELECT run_id,
               model_version,
               league,
               status,
               COALESCE(n_folds, 0)       AS n_folds,
               COALESCE(n_predictions, 0) AS n_predictions,
               started_at,
               completed_at
        FROM backtest_runs
        ORDER BY started_at DESC
        """
    ).pl()


# ---------------------------------------------------------------------------
# Run Detail page
# ---------------------------------------------------------------------------


def run_meta(con: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, Any] | None:
    """Single row from backtest_runs; None if not found."""
    row = con.execute(
        "SELECT run_id, model_version, league, status, n_folds, n_predictions, "
        "started_at, completed_at FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if row is None:
        return None
    keys = [
        "run_id",
        "model_version",
        "league",
        "status",
        "n_folds",
        "n_predictions",
        "started_at",
        "completed_at",
    ]
    return dict(zip(keys, row, strict=False))


def clv_agg(con: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, Any]:
    """Aggregate CLV stats for the header card.

    Re-derives mean_edge_winners and a bootstrap 95% CI from clv_evaluations.
    Returns zeros / None if the run has no evaluations.
    """
    rows = con.execute(
        "SELECT edge_at_close, is_winner FROM clv_evaluations WHERE run_id = ?",
        [run_id],
    ).fetchall()
    if not rows:
        return {
            "n_evaluated": 0,
            "n_winners": 0,
            "mean_edge_winners": None,
            "ci_low": None,
            "ci_high": None,
            "p_value": None,
            "verdict": "INSUFFICIENT_SAMPLE",
        }

    edges = np.array([r[0] for r in rows], dtype=float)
    winners = np.array([bool(r[1]) for r in rows])
    winner_edges = edges[winners]
    n_eval = int(len(edges))
    n_win = int(winners.sum())

    if n_win == 0:
        mean_win = 0.0
        ci_low = ci_high = p_val = None
        verdict = "NO_GO" if n_eval >= 2000 else "INSUFFICIENT_SAMPLE"
    else:
        rng = np.random.default_rng(0)
        boot = np.array(
            [rng.choice(winner_edges, size=n_win, replace=True).mean() for _ in range(2000)]
        )
        mean_win = float(winner_edges.mean())
        ci_low = float(np.percentile(boot, 2.5))
        ci_high = float(np.percentile(boot, 97.5))
        p_val = float((boot <= 0).mean())
        if n_eval < 1000:
            verdict = "INSUFFICIENT_SAMPLE"
        elif n_eval < 2000:
            verdict = "PRELIMINARY_SIGNAL"
        elif mean_win <= 0:
            verdict = "NO_GO"
        elif ci_low <= 0:
            verdict = "MARGINAL_SIGNAL"
        else:
            verdict = "GO"

    return {
        "n_evaluated": n_eval,
        "n_winners": n_win,
        "mean_edge_winners": mean_win if n_win else None,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p_val,
        "verdict": verdict,
    }


def edge_by_season(con: duckdb.DuckDBPyConnection, run_id: str) -> pl.DataFrame:
    """Mean edge (all predictions) grouped by season extracted from fixture_id."""
    return con.execute(
        """
        SELECT split_part(ce.fixture_id, '|', 2) AS season,
               AVG(ce.edge_at_close)              AS mean_edge,
               COUNT(*)                           AS n_predictions
        FROM clv_evaluations ce
        WHERE ce.run_id = ?
        GROUP BY 1
        ORDER BY 1
        """,
        [run_id],
    ).pl()


def reliability_bins_df(con: duckdb.DuckDBPyConnection, run_id: str) -> pl.DataFrame:
    """Reliability bins for all (market, selection) pairs of a run."""
    return con.execute(
        """
        SELECT market, selection, bin_idx, bin_lower, bin_upper,
               n_in_bin, frac_pos, mean_pred, passes_2pp
        FROM reliability_bins
        WHERE run_id = ?
        ORDER BY market, selection, bin_idx
        """,
        [run_id],
    ).pl()


def feature_importances_df(con: duckdb.DuckDBPyConnection, run_id: str) -> pl.DataFrame:
    """Feature importances wide: one row per (fold_rank, feature_name).

    fold_rank is 1-based ordered by xgb_fits.as_of ascending, sampled to at
    most 50 folds when the run has more (evenly spaced).
    """
    meta = con.execute(
        "SELECT started_at, completed_at FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if meta is None:
        return pl.DataFrame(
            schema={
                "fold_rank": pl.Int64,
                "feature_name": pl.Utf8,
                "below_null_baseline": pl.Boolean,
                "permutation_importance": pl.Float64,
            }
        )
    started_at, completed_at = meta

    fits = con.execute(
        """
        SELECT fit_id,
               ROW_NUMBER() OVER (ORDER BY as_of ASC) AS fold_rank
        FROM xgb_fits
        WHERE model_version = 'xgb_ou25_v1'
          AND fitted_at >= ?
          AND fitted_at <= COALESCE(?, fitted_at)
        ORDER BY as_of ASC
        """,
        [started_at, completed_at],
    ).pl()

    if fits.height == 0:
        return pl.DataFrame(
            schema={
                "fold_rank": pl.Int64,
                "feature_name": pl.Utf8,
                "below_null_baseline": pl.Boolean,
                "permutation_importance": pl.Float64,
            }
        )

    # Sample to at most 50 folds
    max_folds = 50
    if fits.height > max_folds:
        step = fits.height / max_folds
        indices = [int(i * step) for i in range(max_folds)]
        fits = fits[indices]

    fit_ids = fits["fit_id"].to_list()
    fold_map = dict(zip(fits["fit_id"].to_list(), fits["fold_rank"].to_list(), strict=False))

    imp = con.execute(
        """
        SELECT fit_id, feature_name, below_null_baseline, permutation_importance
        FROM xgb_feature_importances
        WHERE fit_id = ANY(?)
        """,
        [fit_ids],
    ).pl()

    if imp.height == 0:
        return imp

    fold_map_df = pl.DataFrame(
        {
            "fit_id": list(fold_map.keys()),
            "fold_rank": list(fold_map.values()),
        }
    )
    return imp.join(fold_map_df, on="fit_id", how="left").drop("fit_id")


def clv_bets_df(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    *,
    would_have_bet_only: bool = False,
    page: int = 0,
    page_size: int = 50,
) -> pl.DataFrame:
    """Paginated CLV evaluations, optionally filtered to would_have_bet=True."""
    where_extra = "AND would_have_bet = TRUE" if would_have_bet_only else ""
    offset = page * page_size
    return con.execute(
        f"""
        SELECT fixture_id,
               market,
               selection,
               ROUND(p_raw, 4)                AS p_raw,
               ROUND(p_calibrated, 4)         AS p_calibrated,
               ROUND(pinnacle_close_decimal, 3) AS pinnacle_close,
               ROUND(edge_at_close, 4)        AS edge_at_close,
               is_winner,
               would_have_bet
        FROM clv_evaluations
        WHERE run_id = ? {where_extra}
        ORDER BY ABS(edge_at_close) DESC
        LIMIT ? OFFSET ?
        """,
        [run_id, page_size, offset],
    ).pl()


def clv_bets_count(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    *,
    would_have_bet_only: bool = False,
) -> int:
    where_extra = "AND would_have_bet = TRUE" if would_have_bet_only else ""
    return con.execute(
        f"SELECT COUNT(*) FROM clv_evaluations WHERE run_id = ? {where_extra}",
        [run_id],
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# CLV Explorer page
# ---------------------------------------------------------------------------


def cross_run_clv(
    con: duckdb.DuckDBPyConnection,
    *,
    model_versions: list[str] | None = None,
    season: str | None = None,
    market: str | None = None,
    would_have_bet: bool | None = None,
) -> pl.DataFrame:
    """Cross-run aggregated CLV stats with optional filters.

    Returns one row per run_id with aggregate edge metrics.
    """
    filters = ["1=1"]
    params: list[Any] = []

    if season:
        filters.append("split_part(ce.fixture_id, '|', 2) = ?")
        params.append(season)
    if market:
        filters.append("ce.market = ?")
        params.append(market)
    if would_have_bet is True:
        filters.append("ce.would_have_bet = TRUE")
    elif would_have_bet is False:
        filters.append("ce.would_have_bet = FALSE")

    where_clause = " AND ".join(filters)
    mv_filter = ""
    if model_versions:
        placeholders = ", ".join("?" for _ in model_versions)
        mv_filter = f"AND br.model_version IN ({placeholders})"
        params = params + list(model_versions)

    return con.execute(
        f"""
        SELECT br.run_id,
               br.model_version,
               br.league,
               br.started_at,
               COUNT(ce.evaluation_id)                         AS n_evaluated,
               AVG(ce.edge_at_close)                           AS mean_edge_all,
               AVG(CASE WHEN ce.is_winner THEN ce.edge_at_close END)
                                                               AS mean_edge_winners,
               SUM(ce.would_have_bet::INT)                     AS n_would_have_bet,
               AVG(CASE WHEN ce.would_have_bet THEN ce.edge_at_close END)
                                                               AS mean_edge_whb
        FROM backtest_runs br
        JOIN clv_evaluations ce ON ce.run_id = br.run_id
        WHERE {where_clause} {mv_filter}
        GROUP BY br.run_id, br.model_version, br.league, br.started_at
        ORDER BY br.started_at DESC
        """,
        params,
    ).pl()


def available_seasons(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Distinct seasons present in clv_evaluations (derived from fixture_id)."""
    rows = con.execute(
        "SELECT DISTINCT split_part(fixture_id, '|', 2) AS season "
        "FROM clv_evaluations ORDER BY season"
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def available_markets(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Distinct markets present in clv_evaluations."""
    rows = con.execute("SELECT DISTINCT market FROM clv_evaluations ORDER BY market").fetchall()
    return [r[0] for r in rows if r[0]]


def available_model_versions(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Distinct model_versions from backtest_runs."""
    rows = con.execute(
        "SELECT DISTINCT model_version FROM backtest_runs ORDER BY model_version"
    ).fetchall()
    return [r[0] for r in rows if r[0]]


# ---------------------------------------------------------------------------
# Feature Stability page
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Kelly Sizing page
# ---------------------------------------------------------------------------


def kelly_sizing_df(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    bankroll: float = 1000.0,
) -> pl.DataFrame:
    """Compute hypothetical Kelly stakes for would_have_bet rows.

    Joins clv_evaluations → model_predictions for sigma_p; uses
    pinnacle_close_decimal as proxy odds. Returns one row per would_have_bet
    prediction with columns: fixture_id, selection, odds, p_hat, sigma_p,
    kelly_fraction, stake_gbp.
    """
    from footy_ev.risk.kelly import kelly_fraction_used, kelly_stake

    rows = con.execute(
        """
        SELECT ce.fixture_id,
               ce.market,
               ce.selection,
               ce.p_calibrated                AS p_hat,
               COALESCE(mp.sigma_p, 0.0)      AS sigma_p,
               ce.pinnacle_close_decimal       AS odds,
               ce.edge_at_close,
               ce.is_winner
        FROM clv_evaluations ce
        LEFT JOIN model_predictions mp
            ON mp.prediction_id = ce.prediction_id
        WHERE ce.run_id = ?
          AND ce.would_have_bet = TRUE
          AND ce.pinnacle_close_decimal > 1.0
        ORDER BY ABS(ce.edge_at_close) DESC
        """,
        [run_id],
    ).fetchall()

    if not rows:
        return pl.DataFrame(
            schema={
                "fixture_id": pl.Utf8,
                "market": pl.Utf8,
                "selection": pl.Utf8,
                "p_hat": pl.Float64,
                "sigma_p": pl.Float64,
                "odds": pl.Float64,
                "kelly_fraction": pl.Float64,
                "stake_gbp": pl.Float64,
                "edge_at_close": pl.Float64,
                "is_winner": pl.Boolean,
            }
        )

    result_rows = []
    for fid, market, sel, p_hat, sigma_p, odds, edge, is_winner in rows:
        frac = kelly_fraction_used(float(p_hat), float(sigma_p), float(odds))
        stake = float(kelly_stake(float(p_hat), float(sigma_p), float(odds), bankroll))
        result_rows.append(
            {
                "fixture_id": fid,
                "market": market,
                "selection": sel,
                "p_hat": float(p_hat),
                "sigma_p": float(sigma_p),
                "odds": float(odds),
                "kelly_fraction": frac,
                "stake_gbp": stake,
                "edge_at_close": float(edge),
                "is_winner": bool(is_winner),
            }
        )

    return pl.DataFrame(result_rows)


def ruin_sim_results(
    edge_pct: float,
    edge_se: float,
    kelly_fraction: float = 0.25,
    n_bets: int = 1_000,
    n_sims: int = 5_000,
) -> dict:
    """Run ruin simulation and return results dict (no DB access)."""
    from footy_ev.risk.ruin import simulate_ruin

    return simulate_ruin(
        edge_pct, edge_se, kelly_fraction, n_bets=n_bets, n_sims=n_sims, rng_seed=0
    )


def feature_stability_df(con: duckdb.DuckDBPyConnection, run_id: str) -> pl.DataFrame:
    """Long-format permutation importances across folds for all features.

    Returns columns: fold_rank (1-based), feature_name, permutation_importance,
    below_null_baseline, as_of. Ordered by fold_rank, feature_name.
    """
    meta = con.execute(
        "SELECT started_at, completed_at FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if meta is None:
        return pl.DataFrame(
            schema={
                "fold_rank": pl.Int64,
                "as_of": pl.Datetime,
                "feature_name": pl.Utf8,
                "permutation_importance": pl.Float64,
                "below_null_baseline": pl.Boolean,
            }
        )
    started_at, completed_at = meta

    return con.execute(
        """
        WITH ranked AS (
            SELECT fit_id,
                   as_of,
                   ROW_NUMBER() OVER (ORDER BY as_of ASC) AS fold_rank
            FROM xgb_fits
            WHERE model_version = 'xgb_ou25_v1'
              AND fitted_at >= ?
              AND fitted_at <= COALESCE(?, fitted_at)
        )
        SELECT r.fold_rank,
               r.as_of,
               fi.feature_name,
               fi.permutation_importance,
               fi.below_null_baseline
        FROM ranked r
        JOIN xgb_feature_importances fi ON fi.fit_id = r.fit_id
        ORDER BY r.fold_rank, fi.feature_name
        """,
        [started_at, completed_at],
    ).pl()


# ---------------------------------------------------------------------------
# Paper Trading page (Phase 3 step 1)
# ---------------------------------------------------------------------------


def paper_bets_recent(con: duckdb.DuckDBPyConnection, limit: int = 50) -> pl.DataFrame:
    """Recent paper_bets rows for the live ticker."""
    return con.execute(
        """
        SELECT decided_at, fixture_id, market, selection, odds_at_decision,
               edge_pct, stake_gbp, settlement_status, p_calibrated, venue
        FROM paper_bets
        ORDER BY decided_at DESC LIMIT ?
        """,
        [limit],
    ).pl()


def paper_bets_total(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute("SELECT COUNT(*) FROM paper_bets").fetchone()
    return int(row[0]) if row else 0


def freshness_per_source(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Latest staleness reading per (venue, fixture) from live_odds_snapshots."""
    return con.execute(
        """
        SELECT venue, fixture_id,
               MAX(received_at) AS latest_received_at,
               MAX(staleness_seconds) AS max_staleness_sec
        FROM live_odds_snapshots
        GROUP BY venue, fixture_id
        ORDER BY latest_received_at DESC NULLS LAST
        LIMIT 20
        """
    ).pl()


def circuit_breaker_status(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Latest breaker state: is_tripped, last_event, recovered_at."""
    row = con.execute(
        """
        SELECT event_id, tripped_at, reason, affected_source,
               max_staleness_sec, auto_recovered, recovered_at
        FROM circuit_breaker_log
        ORDER BY tripped_at DESC LIMIT 1
        """
    ).fetchone()
    if row is None:
        return {"is_tripped": False, "last_event": None, "recovered_at": None}
    is_tripped = not bool(row[5]) and row[6] is None
    return {
        "is_tripped": is_tripped,
        "last_event": {
            "event_id": row[0],
            "tripped_at": row[1],
            "reason": row[2],
            "affected_source": row[3],
            "max_staleness_sec": row[4],
        },
        "recovered_at": row[6],
    }


def edge_distribution_paper(con: duckdb.DuckDBPyConnection, n: int = 100) -> pl.DataFrame:
    """Edge distribution of the most recent N paper bets."""
    return con.execute(
        """
        SELECT edge_pct
        FROM paper_bets
        ORDER BY decided_at DESC LIMIT ?
        """,
        [n],
    ).pl()


def paper_pnl_vs_clv(con: duckdb.DuckDBPyConnection, lookback_days: int = 7) -> pl.DataFrame:
    """Daily aggregate of settled paper_bets pnl and clv_pct."""
    # `lookback_days` is operator-supplied int; coerce + interpolate via
    # f-string (DuckDB INTERVAL wants a literal, not a parameter).
    days = int(lookback_days)
    return con.execute(
        f"""
        SELECT DATE_TRUNC('day', decided_at) AS day,
               SUM(pnl_gbp) AS total_pnl_gbp,
               AVG(clv_pct) AS avg_clv_pct,
               COUNT(*) AS n_bets
        FROM paper_bets
        WHERE decided_at >= CURRENT_TIMESTAMP - INTERVAL '{days} days'
          AND settlement_status <> 'pending'
        GROUP BY 1
        ORDER BY 1
        """
    ).pl()


def fixture_queue(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Distinct fixtures from the most recent invocation."""
    return con.execute(
        """
        SELECT UNNEST(fixture_ids) AS fixture_id, started_at
        FROM langgraph_checkpoint_summaries
        ORDER BY started_at DESC LIMIT 1
        """
    ).pl()


def production_model_info(con: duckdb.DuckDBPyConnection) -> dict[str, Any] | None:
    """Return metadata about the latest completed xgb_ou25_v1 run and its fits.

    Returns None if no qualifying run exists (backtest not yet run).
    """
    run_row = con.execute(
        """
        SELECT run_id, started_at, completed_at
        FROM backtest_runs
        WHERE model_version = 'xgb_ou25_v1'
          AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
        """
    ).fetchone()
    if run_row is None:
        return None

    run_id, started_at, completed_at = run_row

    fit_row = con.execute(
        """
        SELECT model_version, MAX(as_of) AS latest_fold_as_of,
               MAX(fitted_at) AS latest_fitted_at,
               COUNT(*) AS n_folds,
               SUM(n_train) AS total_n_train
        FROM xgb_fits
        WHERE model_version = 'xgb_ou25_v1'
          AND fitted_at >= ?
          AND (? IS NULL OR fitted_at <= ?)
        """,
        [started_at, completed_at, completed_at],
    ).fetchone()

    n_predictions = con.execute(
        "SELECT COUNT(*) FROM model_predictions WHERE run_id = ?", [run_id]
    ).fetchone()[0]

    mean_edge = con.execute(
        """
        SELECT AVG(edge_at_close)
        FROM clv_evaluations
        WHERE run_id = ? AND market = 'ou_2.5'
        """,
        [run_id],
    ).fetchone()[0]

    return {
        "run_id": run_id,
        "model_version": (fit_row[0] if fit_row else "xgb_ou25_v1"),
        "latest_fold_as_of": fit_row[1] if fit_row else None,
        "latest_fitted_at": fit_row[2] if fit_row else None,
        "n_folds": int(fit_row[3]) if fit_row and fit_row[3] else 0,
        "total_n_train": int(fit_row[4]) if fit_row and fit_row[4] else 0,
        "n_predictions": int(n_predictions),
        "mean_edge_pct": float(mean_edge) if mean_edge is not None else None,
    }
