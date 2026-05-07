"""Typer CLI + orchestrator for backtest run evaluation.

Top-level entry: `evaluate_run(con, run_id, *, devig_method, no_calibrate)`
orchestrates calibration, CLV computation, reliability binning, bootstrap CI,
and Markdown report. The Typer command wraps it for shell invocation.

Invocation:
    uv run python -m footy_ev.eval.cli evaluate-run --run-id <uuid>
    uv run python -m footy_ev.eval.cli evaluate-run --run-id <uuid> --no-calibrate

Or via make.ps1:
    .\\make.ps1 evaluate-run -RunId <uuid>
    .\\make.ps1 evaluate-run -RunId <uuid> -NoCalibrate
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl
import typer

from footy_ev.db import apply_migrations, apply_views
from footy_ev.eval.bootstrap import bootstrap_edge_ci
from footy_ev.eval.calibrate import (
    fit_isotonic_walk_forward,
    persist_calibration_fits,
)
from footy_ev.eval.clv import compute_clv
from footy_ev.eval.devig import DevigMethod
from footy_ev.eval.reliability import reliability_bins, reliability_pass_pct
from footy_ev.eval.report import write_markdown_report
from footy_ev.risk.kelly import kelly_stake

app = typer.Typer(add_completion=False, help="footy-ev backtest evaluation.")


@app.callback()  # type: ignore[misc]
def _callback() -> None:
    """Force Typer into subcommand-dispatch mode (see backtest/cli.py)."""


DEFAULT_DB_PATH = Path("data/warehouse/footy_ev.duckdb")
REPORTS_DIR = Path("reports")


def _open_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    apply_views(con)
    return con


def _persist_reliability_bins(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    market: str,
    selection: str,
    bins_df: pl.DataFrame,
) -> None:
    rows = []
    for r in bins_df.iter_rows(named=True):
        rows.append(
            (
                run_id,
                market,
                selection,
                int(r["bin_idx"]),
                float(r["bin_lower"]),
                float(r["bin_upper"]),
                int(r["n_in_bin"]),
                r["frac_pos"],
                r["mean_pred"],
                r["passes_2pp"],
            )
        )
    con.executemany(
        """
        INSERT INTO reliability_bins (
            run_id, market, selection, bin_idx, bin_lower, bin_upper,
            n_in_bin, frac_pos, mean_pred, passes_2pp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _classify_verdict(
    n_eval: int,
    mean_edge_winners: float,
    ci_low: float,
) -> str:
    """Classify go/no-go verdict using n_eval, mean edge, and bootstrap CI.

    Tiers (evaluated in order):
        INSUFFICIENT_SAMPLE: n_eval < 1000 or mean not finite.
        PRELIMINARY_SIGNAL:  1000 <= n_eval < 2000.
        NO_GO:               n_eval >= 2000 and mean <= 0.
        MARGINAL_SIGNAL:     n_eval >= 2000 and mean > 0 and ci_low <= 0.
        GO:                  n_eval >= 2000 and mean > 0 and ci_low > 0.
    """
    if n_eval < 1000:
        return "INSUFFICIENT_SAMPLE"
    if n_eval < 2000:
        return "PRELIMINARY_SIGNAL"
    if not np.isfinite(mean_edge_winners):
        return "INSUFFICIENT_SAMPLE"
    if mean_edge_winners <= 0:
        return "NO_GO"
    # mean > 0; distinguish structural from marginal by CI lower bound.
    if not np.isfinite(ci_low) or ci_low <= 0:
        return "MARGINAL_SIGNAL"
    return "GO"


def _compute_kelly_sizing(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    bankroll: float = 1000.0,
) -> dict[str, Any]:
    """Compute hypothetical Kelly stakes for would_have_bet rows.

    Joins clv_evaluations to model_predictions to get sigma_p and
    pinnacle_close_decimal (used as proxy odds). Returns distribution stats.
    No DB writes.
    """
    rows = con.execute(
        """
        SELECT ce.p_calibrated,
               COALESCE(mp.sigma_p, 0.0)      AS sigma_p,
               ce.pinnacle_close_decimal
        FROM clv_evaluations ce
        LEFT JOIN model_predictions mp
            ON mp.prediction_id = ce.prediction_id
        WHERE ce.run_id = ?
          AND ce.would_have_bet = TRUE
          AND ce.pinnacle_close_decimal IS NOT NULL
          AND ce.pinnacle_close_decimal > 1.0
        """,
        [run_id],
    ).fetchall()

    if not rows:
        return {"kelly_n_sized": 0}

    stakes = []
    for p_cal, sigma_p, odds in rows:
        stake = kelly_stake(
            float(p_cal),
            float(sigma_p),
            float(odds),
            bankroll,
            base_fraction=0.25,
            uncertainty_k=1.0,
            per_bet_cap_pct=0.02,
            recent_clv_pct=0.0,
        )
        stakes.append(float(stake))

    arr = np.array(stakes, dtype=float)
    nonzero = arr[arr > 0]
    return {
        "kelly_n_sized": int(len(arr)),
        "kelly_n_nonzero": int(len(nonzero)),
        "kelly_mean_stake": float(nonzero.mean()) if len(nonzero) else 0.0,
        "kelly_p50_stake": float(np.percentile(nonzero, 50)) if len(nonzero) else 0.0,
        "kelly_p95_stake": float(np.percentile(nonzero, 95)) if len(nonzero) else 0.0,
        "kelly_total_turnover": float(arr.sum()),
        "kelly_bankroll_used": bankroll,
        "kelly_stakes_dist": arr.tolist(),
    }


def evaluate_run(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    *,
    devig_method: DevigMethod = "shin",
    reports_dir: Path = REPORTS_DIR,
    no_calibrate: bool = False,
    kelly_bankroll: float = 1000.0,
) -> dict[str, Any]:
    """Orchestrate calibration -> CLV -> reliability -> bootstrap -> report.

    Args:
        con: open DuckDB connection (with migrations + views applied).
        run_id: identifier in backtest_runs.
        devig_method: 'shin' (default) or 'power'.
        reports_dir: directory for Markdown output.
        no_calibrate: if True, skip isotonic fitting; p_calibrated = p_raw.

    Returns:
        Structured summary dict (also rendered to reports/run_<run_id>.md).

    Raises:
        ValueError: if run_id is not found in backtest_runs.
    """
    run_row = con.execute(
        "SELECT model_version, league, n_folds, n_predictions FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if run_row is None:
        raise ValueError(f"run_id not found in backtest_runs: {run_id}")
    model_version, league, n_folds, n_predictions = run_row

    # Idempotency: wipe prior evaluation data for this run so re-runs
    # (e.g. with --no-calibrate) don't hit PK violations.
    con.execute("DELETE FROM clv_evaluations  WHERE run_id = ?", [run_id])
    con.execute("DELETE FROM calibration_fits WHERE run_id = ?", [run_id])
    con.execute("DELETE FROM reliability_bins  WHERE run_id = ?", [run_id])

    if no_calibrate:
        calibrated_probs: dict[str, float] = {}
        cal_state: dict[str, Any] = {}
    else:
        calibrated_probs, cal_state = fit_isotonic_walk_forward(con, run_id)
        persist_calibration_fits(con, run_id, cal_state)

    clv_summary = compute_clv(con, run_id, calibrated_probs, devig_method=devig_method)

    # Discover (market, selection) pairs from clv_evaluations (populated
    # after compute_clv). Reliability bins are computed on p_calibrated from
    # clv_evaluations (= p_raw when no_calibrate=True).
    ms_pairs = con.execute(
        "SELECT DISTINCT market, selection FROM clv_evaluations WHERE run_id = ?",
        [run_id],
    ).fetchall()

    # reliability_dfs keyed by "<market>:<selection>".
    reliability_dfs: dict[str, pl.DataFrame] = {}
    rel_pass_pct: dict[str, float] = {}
    for market, sel in ms_pairs:
        rows = con.execute(
            "SELECT p_calibrated, is_winner FROM clv_evaluations "
            "WHERE run_id = ? AND market = ? AND selection = ?",
            [run_id, market, sel],
        ).fetchall()
        if not rows:
            continue
        key = f"{market}:{sel}"
        p_arr = np.array([r[0] for r in rows], dtype=float)
        y_arr = np.array([r[1] for r in rows], dtype=bool)
        bins_df = reliability_bins(p_arr, y_arr)
        _persist_reliability_bins(con, run_id, market, sel, bins_df)
        reliability_dfs[key] = bins_df
        rel_pass_pct[key] = reliability_pass_pct(bins_df)

    brier_raw = {sel: float(s["brier_raw"]) for sel, s in cal_state.items()}
    brier_cal = {sel: float(s["brier_calibrated"]) for sel, s in cal_state.items()}

    bootstrap = bootstrap_edge_ci(con, run_id)

    n_eval = clv_summary["n_evaluated"]
    verdict = _classify_verdict(n_eval, clv_summary["mean_edge_winners"], bootstrap["ci_low"])

    summary = {
        "run_id": run_id,
        "league": league,
        "model_version": model_version,
        "n_folds": n_folds,
        "n_predictions": n_predictions,
        "devig_method": devig_method,
        "no_calibrate": no_calibrate,
        **clv_summary,
        "brier_raw_by_selection": brier_raw,
        "brier_calibrated_by_selection": brier_cal,
        "reliability_pass_pct_by_selection": rel_pass_pct,
        "bootstrap_mean": bootstrap["mean"],
        "bootstrap_ci_low": bootstrap["ci_low"],
        "bootstrap_ci_high": bootstrap["ci_high"],
        "bootstrap_p_value_above_zero": bootstrap["p_value_above_zero"],
        "bootstrap_n_winners": bootstrap["n_winners"],
        "bootstrap_n_resamples": bootstrap["n_resamples"],
        "go_no_go_verdict": verdict,
    }

    kelly_sizing = _compute_kelly_sizing(con, run_id, bankroll=kelly_bankroll)
    summary.update(kelly_sizing)

    out_path = reports_dir / f"run_{run_id}.md"
    write_markdown_report(summary, reliability_dfs, out_path)
    summary["report_path"] = str(out_path)
    return summary


@app.command("evaluate-run")  # type: ignore[misc]
def evaluate_run_cli(
    run_id: str = typer.Option(..., "--run-id"),
    devig_method: str = typer.Option("shin", "--devig-method"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
    no_calibrate: bool = typer.Option(False, "--no-calibrate", is_flag=True),
    kelly_bankroll: float = typer.Option(
        1000.0, "--kelly-bankroll", help="Placeholder bankroll for Kelly sizing (£)"
    ),
) -> None:
    """Run end-to-end evaluation for a backtest run."""
    con = _open_db(db_path)
    summary = evaluate_run(
        con,
        run_id,
        devig_method=devig_method,
        no_calibrate=no_calibrate,
        kelly_bankroll=kelly_bankroll,
    )
    typer.echo(
        f"verdict={summary['go_no_go_verdict']} "
        f"n_evaluated={summary['n_evaluated']:,} "
        f"mean_edge_winners={summary['mean_edge_winners']:+.4f} "
        f"CI=[{summary['bootstrap_ci_low']:+.4f},{summary['bootstrap_ci_high']:+.4f}] "
        f"p={summary['bootstrap_p_value_above_zero']:.3f} "
        f"report={summary['report_path']}"
    )
    if summary.get("kelly_n_sized", 0) > 0:
        typer.echo(
            f"kelly n_sized={summary['kelly_n_sized']:,} "
            f"n_nonzero={summary.get('kelly_n_nonzero', 0):,} "
            f"mean_stake=£{summary.get('kelly_mean_stake', 0):.2f} "
            f"total_turnover=£{summary.get('kelly_total_turnover', 0):.2f} "
            f"(bankroll=£{kelly_bankroll:.0f})"
        )


@app.command("diagnose-features")  # type: ignore[misc]
def diagnose_features_cli(
    run_id: str = typer.Option(..., "--run-id"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
) -> None:
    """Replay snapshot assembler over an XGBoost run; report xg_skellam_p_over distribution."""
    from footy_ev.eval.diagnostics import feature_sanity

    con = _open_db(db_path)
    stats = feature_sanity(con, run_id)
    typer.echo(f"xgb_run_id        = {stats['xgb_run_id']}")
    typer.echo(f"xg_skellam_run_id = {stats['xg_skellam_run_id']}")
    typer.echo(f"n_folds           = {stats['n_folds']}")
    typer.echo(f"n_rows            = {stats['n_rows']:,}")
    typer.echo(f"n_at_default_0.5  = {stats['n_at_default']:,} ({stats['frac_at_default']:.1%})")
    typer.echo(f"min               = {stats['min']:.6f}")
    typer.echo(f"max               = {stats['max']:.6f}")
    typer.echo(f"mean              = {stats['mean']:.6f}")
    typer.echo(f"median            = {stats['median']:.6f}")
    typer.echo(
        f"stddev            = {stats['stddev']:.6f}"
        if stats["stddev"] is not None
        else "stddev = n/a"
    )


@app.command("diagnose-shap")  # type: ignore[misc]
def diagnose_shap_cli(
    run_id: str = typer.Option(..., "--run-id"),
    fold_idx: int = typer.Option(-1, "--fold-idx"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
) -> None:
    """Compute mean(|SHAP|) per feature on one fold's test set; rank descending."""
    from footy_ev.eval.diagnostics import shap_importance

    con = _open_db(db_path)
    ranking = shap_importance(con, run_id, fold_idx=fold_idx)
    typer.echo(f"{'feature_name':<32} {'mean_abs_shap':>14}")
    typer.echo("-" * 48)
    for r in ranking.iter_rows(named=True):
        typer.echo(f"{r['feature_name']:<32} {r['mean_abs_shap']:>14.6f}")


if __name__ == "__main__":
    app()
