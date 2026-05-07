"""Top-level orchestrator for footy-ev canonical pipeline.

Pure orchestration — calls into existing library functions. No business logic.

Subcommands:
    canonical  Run xG-Skellam (if needed) → XGBoost → evaluate → print verdict.
    dashboard  Launch Streamlit dashboard.
    status     Print latest backtest_runs row + verdict + counts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb
import typer

from footy_ev.backtest.walkforward import run_backtest
from footy_ev.db import apply_migrations, apply_views
from footy_ev.eval.cli import evaluate_run

app = typer.Typer(add_completion=False, help="footy-ev canonical pipeline orchestrator.")

DEFAULT_DB_PATH = Path("data/warehouse/footy_ev.duckdb")


def _open_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    apply_views(con)
    return con


def _latest_run_id(con: duckdb.DuckDBPyConnection, model_version: str) -> str | None:
    row = con.execute(
        """
        SELECT run_id FROM backtest_runs
        WHERE model_version = ? AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST LIMIT 1
        """,
        [model_version],
    ).fetchone()
    return row[0] if row else None


@app.command("canonical")
def canonical(
    league: str = typer.Option("EPL", "--league"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
) -> None:
    """Run the canonical thesis-test pipeline end-to-end."""
    con = _open_db(db_path)

    skellam_run_id = _latest_run_id(con, "xg_skellam_v1")
    if skellam_run_id is None:
        typer.echo("[canonical] no Skellam run found; running xG-Skellam backtest...")
        skellam_run_id = run_backtest(
            con,
            league,
            train_min_seasons=3,
            step_days=7,
            model_version="xg_skellam_v1",
            xi_decay=0.0,
        )
        typer.echo(f"[canonical] xG-Skellam run_id={skellam_run_id}")
    else:
        typer.echo(f"[canonical] reusing Skellam run_id={skellam_run_id}")

    typer.echo("[canonical] running XGBoost backtest stacked on Skellam...")
    xgb_run_id = run_backtest(
        con,
        league,
        train_min_seasons=3,
        step_days=7,
        model_version="xgb_ou25_v1",
        xi_decay=0.0,
        xg_skellam_run_id=skellam_run_id,
    )
    typer.echo(f"[canonical] XGBoost run_id={xgb_run_id}")

    typer.echo("[canonical] evaluating XGBoost run (no calibration)...")
    summary = evaluate_run(con, xgb_run_id, no_calibrate=True)

    verdict = summary.get("verdict", "?")
    mean = summary.get("mean_edge_winners", float("nan"))
    ci_low = summary.get("ci_low", float("nan"))
    ci_high = summary.get("ci_high", float("nan"))
    pval = summary.get("p_value", float("nan"))
    n_eval = summary.get("n_evaluations", 0)

    typer.echo("")
    typer.echo("=" * 60)
    typer.echo(f"verdict       = {verdict}")
    typer.echo(f"mean_edge     = {mean:+.4f}")
    typer.echo(f"95% CI        = [{ci_low:+.4f}, {ci_high:+.4f}]")
    typer.echo(f"p-value       = {pval:.4f}")
    typer.echo(f"n_evaluations = {n_eval}")
    typer.echo("=" * 60)
    typer.echo("dashboard     : .\\make.ps1 dashboard  (or http://localhost:8501)")


@app.command("dashboard")
def dashboard() -> None:
    """Launch the Streamlit dashboard."""
    subprocess.run(
        ["uv", "run", "streamlit", "run", "dashboard/app.py"],
        check=False,
    )


@app.command("status")
def status(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
) -> None:
    """Print latest run state, verdict, and counts."""
    con = _open_db(db_path)

    row = con.execute(
        """
        SELECT run_id, model_version, status, started_at, completed_at,
               n_folds, n_predictions
        FROM backtest_runs
        ORDER BY started_at DESC NULLS LAST LIMIT 1
        """
    ).fetchone()
    if row is None:
        typer.echo("no backtest_runs rows yet.")
        return

    run_id, mv, st, started, completed, n_folds, n_preds = row
    typer.echo(f"latest_run_id   = {run_id}")
    typer.echo(f"model_version   = {mv}")
    typer.echo(f"status          = {st}")
    typer.echo(f"started_at      = {started}")
    typer.echo(f"completed_at    = {completed}")
    typer.echo(f"n_folds         = {n_folds}")
    typer.echo(f"n_predictions   = {n_preds}")

    n_eval = con.execute(
        "SELECT COUNT(*) FROM clv_evaluations WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    typer.echo(f"n_evaluations   = {n_eval}")

    last_fit = con.execute("SELECT MAX(fitted_at) FROM xgb_fits").fetchone()[0]
    typer.echo(f"last_xgb_fit    = {last_fit}")


if __name__ == "__main__":
    app()
