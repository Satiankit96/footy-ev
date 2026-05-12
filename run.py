"""footy-ev unified runner.

Usage:
  uv run python run.py                            # one pipeline cycle, exit
  uv run python run.py loop --interval-min 15     # cycles every N minutes
  uv run python run.py dashboard                  # launch Streamlit dashboard
  uv run python run.py status                     # print state, no pipeline run
  uv run python run.py bootstrap                  # refresh Kalshi aliases

Existing subcommands (canonical, paper-trade, paper-status) are preserved so
`make.ps1` targets keep working. Business logic stays in src/footy_ev/ —
run.py imports and orchestrates only.

Default venue per .env. LIVE_TRADING=true refused until Phase 4 conditions met.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import typer

from footy_ev.backtest.walkforward import run_backtest
from footy_ev.db import apply_migrations, apply_views
from footy_ev.eval.cli import evaluate_run
from footy_ev.runtime.status import DEMO_BASE_URL, print_status_table

app = typer.Typer(add_completion=False, help="footy-ev unified runner.")

DEFAULT_DB_PATH = Path("data/warehouse/footy_ev.duckdb")
DASHBOARD_APP_PATH = (Path(__file__).resolve().parent / "dashboard" / "app.py").resolve()


def _refuse_if_live_trading() -> None:
    if os.environ.get("LIVE_TRADING", "").lower() in {"true", "1", "yes"}:
        typer.echo(
            "LIVE_TRADING is enabled but Phase 4 conditions are not validated. "
            "Unset to proceed in paper mode."
        )
        raise typer.Exit(code=1)


def _require_kalshi_env() -> None:
    if not os.environ.get("KALSHI_API_KEY_ID"):
        typer.echo("KALSHI_API_KEY_ID is not set. Copy .env.example to .env and fill it in.")
        raise typer.Exit(code=1)
    pem_path = Path(os.environ.get("KALSHI_PRIVATE_KEY_PATH", "data/kalshi_private_key.pem"))
    if not pem_path.exists():
        typer.echo(
            f"Kalshi private key not found at {pem_path}. "
            "Set KALSHI_PRIVATE_KEY_PATH or place the PEM at data/kalshi_private_key.pem."
        )
        raise typer.Exit(code=1)


def _warn_if_base_url_unset() -> None:
    if not os.environ.get("KALSHI_API_BASE_URL"):
        typer.echo(f"WARN: KALSHI_API_BASE_URL unset; defaulting to {DEMO_BASE_URL}")


@app.callback(invoke_without_command=True)  # type: ignore[misc]
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        cycle()


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


def _run_cycle() -> dict[str, Any]:
    from footy_ev.runtime import PaperTraderConfig, run_once

    cfg = PaperTraderConfig(db_path=DEFAULT_DB_PATH)
    return run_once(cfg)


@app.command("cycle")  # type: ignore[misc]
def cycle() -> None:
    """Run one end-to-end paper-trader pipeline cycle and print the state table."""
    _refuse_if_live_trading()
    _require_kalshi_env()
    _warn_if_base_url_unset()
    out = _run_cycle()
    typer.echo(
        f"\nCycle complete: invocation={out['invocation_id']} "
        f"candidates={out['n_candidates']} approved={out['n_approved']} "
        f"breaker={out['breaker_tripped']}"
    )
    if out.get("last_error"):
        typer.echo(f"last_error: {out['last_error']}")
    print_status_table(_open_db(DEFAULT_DB_PATH), emit=typer.echo)


@app.command("loop")  # type: ignore[misc]
def loop(interval_min: int = typer.Option(15, "--interval-min", min=1)) -> None:
    """Run cycles every N minutes. Ctrl+C to stop after the current cycle."""
    _refuse_if_live_trading()
    _require_kalshi_env()
    _warn_if_base_url_unset()
    typer.echo(f"loop: every {interval_min} min. Ctrl+C to stop.")
    try:
        while True:
            out = _run_cycle()
            typer.echo(
                f"[{datetime.now(tz=UTC).isoformat()}] cycle: "
                f"candidates={out['n_candidates']} approved={out['n_approved']} "
                f"breaker={out['breaker_tripped']}"
            )
            time.sleep(interval_min * 60)
    except KeyboardInterrupt:
        typer.echo("\nStopping after current cycle...")
        raise typer.Exit(code=0) from None


@app.command("bootstrap")  # type: ignore[misc]
def bootstrap() -> None:
    """Refresh Kalshi event-ticker to fixture aliases (bootstrap_kalshi_aliases --live)."""
    _refuse_if_live_trading()
    _require_kalshi_env()
    _warn_if_base_url_unset()
    sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
    from bootstrap_kalshi_aliases import main as bootstrap_main  # type: ignore[import-not-found]

    rc = bootstrap_main(["--live"])
    raise typer.Exit(code=rc)


@app.command("status")  # type: ignore[misc]
def status(db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path")) -> None:
    """Print pipeline state - no API calls, warehouse-only."""
    print_status_table(_open_db(db_path), emit=typer.echo)


# --- Legacy subcommands preserved for make.ps1 compatibility ----------------
@app.command("canonical")  # type: ignore[misc]
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


@app.command("paper-trade")  # type: ignore[misc]
def paper_trade(
    fixtures_ahead_days: int = typer.Option(7, "--fixtures-ahead-days"),
    bankroll: float = typer.Option(1000.0, "--bankroll"),
    edge_threshold: float = typer.Option(0.03, "--edge-threshold"),
    once: bool = typer.Option(False, "--once", help="Single-pass test (no loop)."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
    model_run_id: str | None = typer.Option(None, "--model-run-id"),
) -> None:
    """Start the paper-trading runtime (foreground; Ctrl-C to stop)."""
    from footy_ev.runtime import PaperTraderConfig, run_forever, run_once

    effective_run_id = model_run_id or os.environ.get("PAPER_TRADER_MODEL_RUN_ID")
    cfg = PaperTraderConfig(
        fixtures_ahead_days=fixtures_ahead_days,
        bankroll_gbp=bankroll,
        edge_threshold_pct=edge_threshold,
        db_path=db_path,
        model_run_id=effective_run_id,
    )
    if once:
        out = run_once(cfg)
        typer.echo(
            f"paper-trade --once: invocation={out['invocation_id']} "
            f"fixtures={out['n_fixtures']} candidates={out['n_candidates']} "
            f"approved={out['n_approved']} breaker={out['breaker_tripped']}"
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
def paper_status(db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path")) -> None:
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


@app.command("dashboard")  # type: ignore[misc]
def dashboard() -> None:
    """Launch the Streamlit dashboard."""
    subprocess.run(
        ["uv", "run", "streamlit", "run", str(DASHBOARD_APP_PATH)],
        check=False,
    )


if __name__ == "__main__":
    app()
