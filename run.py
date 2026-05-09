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


@app.callback(invoke_without_command=True)  # type: ignore[misc]
def _root(ctx: typer.Context) -> None:
    """Print help when invoked with no subcommand."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        typer.echo(
            "\nTry `python run.py status` for a quick overview, "
            "or `python run.py --help` for all commands."
        )


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


DASHBOARD_APP_PATH = (Path(__file__).resolve().parent / "dashboard" / "app.py").resolve()


@app.command("paper-trade")  # type: ignore[misc]
def paper_trade(
    fixtures_ahead_days: int = typer.Option(7, "--fixtures-ahead-days"),
    bankroll: float = typer.Option(1000.0, "--bankroll"),
    edge_threshold: float = typer.Option(0.03, "--edge-threshold"),
    once: bool = typer.Option(False, "--once", help="Single-pass test (no loop)."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
) -> None:
    """Start the paper-trading runtime (foreground; Ctrl-C to stop)."""
    from footy_ev.runtime import PaperTraderConfig, run_forever, run_once

    cfg = PaperTraderConfig(
        fixtures_ahead_days=fixtures_ahead_days,
        bankroll_gbp=bankroll,
        edge_threshold_pct=edge_threshold,
        db_path=db_path,
    )
    if once:
        out = run_once(cfg)
        typer.echo(
            "paper-trade --once: "
            f"invocation={out['invocation_id']} "
            f"fixtures={out['n_fixtures']} "
            f"candidates={out['n_candidates']} "
            f"approved={out['n_approved']} "
            f"breaker={out['breaker_tripped']}"
        )
        if out["last_error"]:
            typer.echo(f"last_error: {out['last_error']}")
        return
    typer.echo(
        f"paper-trade: polling every {cfg.tick_seconds}s, "
        f"fixtures-ahead-days={cfg.fixtures_ahead_days}, "
        f"bankroll={cfg.bankroll_gbp} GBP, "
        f"edge-threshold={cfg.edge_threshold_pct:.1%}. Ctrl-C to stop."
    )
    run_forever(cfg)


@app.command("paper-status")  # type: ignore[misc]
def paper_status(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
) -> None:
    """Print latest paper-trading invocation, recent bets, breaker state."""
    con = _open_db(db_path)
    inv = con.execute(
        """
        SELECT invocation_id, started_at, completed_at, final_node,
               n_candidate_bets, n_approved_bets, breaker_tripped, breaker_reason
        FROM langgraph_checkpoint_summaries
        ORDER BY started_at DESC LIMIT 1
        """
    ).fetchone()
    if inv is None:
        typer.echo("no paper-trading invocations yet.")
    else:
        (inv_id, started, completed, final_node, n_c, n_a, breaker, reason) = inv
        typer.echo(f"latest_invocation = {inv_id}")
        typer.echo(f"started_at        = {started}")
        typer.echo(f"completed_at      = {completed}")
        typer.echo(f"final_node        = {final_node}")
        typer.echo(f"n_candidates      = {n_c}")
        typer.echo(f"n_approved        = {n_a}")
        typer.echo(f"breaker_tripped   = {breaker}")
        if breaker:
            typer.echo(f"breaker_reason    = {reason}")

    n_paper = con.execute("SELECT COUNT(*) FROM paper_bets").fetchone()[0]
    typer.echo(f"total_paper_bets  = {n_paper}")

    last_bets = con.execute(
        """
        SELECT decided_at, fixture_id, market, selection, odds_at_decision,
               edge_pct, stake_gbp
        FROM paper_bets
        ORDER BY decided_at DESC LIMIT 5
        """
    ).fetchall()
    if last_bets:
        typer.echo("recent paper bets:")
        for r in last_bets:
            typer.echo(
                f"  {r[0]}  {r[1]}  {r[2]}/{r[3]}  odds={r[4]:.2f} edge={r[5]:+.2%} stake=GBP{r[6]}"
            )


@app.command("dashboard")
def dashboard() -> None:
    """Launch the Streamlit dashboard."""
    subprocess.run(
        ["uv", "run", "streamlit", "run", str(DASHBOARD_APP_PATH)],
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
