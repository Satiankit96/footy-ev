"""Typer CLI for backtest commands.

Invocation:
    uv run python -m footy_ev.backtest.cli backtest-walkforward \\
        --league EPL --train-min-seasons 3 --step-days 7
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import typer

from footy_ev.backtest.walkforward import MODEL_VERSION_DEFAULT, run_backtest
from footy_ev.db import apply_migrations, apply_views

app = typer.Typer(add_completion=False, help="footy-ev backtest commands.")


@app.callback()  # type: ignore[misc]
def _callback() -> None:
    """Force Typer into subcommand-dispatch mode (otherwise a single-command
    app implicitly runs its only command and treats the subcommand name as
    a positional argument)."""


DEFAULT_DB_PATH = Path("data/warehouse/footy_ev.duckdb")


def _open_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    apply_views(con)
    return con


@app.command("backtest-walkforward")  # type: ignore[misc]
def backtest_walkforward(
    league: str = typer.Option("EPL", "--league"),
    train_min_seasons: int = typer.Option(3, "--train-min-seasons"),
    step_days: int = typer.Option(7, "--step-days"),
    model_version: str = typer.Option(MODEL_VERSION_DEFAULT, "--model-version"),
    xi_decay: float = typer.Option(0.0019, "--xi-decay"),
    xg_skellam_run_id: str = typer.Option("", "--xg-skellam-run-id"),
    feature_subset: str = typer.Option(
        "",
        "--feature-subset",
        help=(
            "Comma-separated subset of FEATURE_NAMES to use (XGBoost only). "
            "Empty (default) = all features."
        ),
    ),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path"),
) -> None:
    """Run a walk-forward backtest and persist outputs."""
    con = _open_db(db_path)
    subset_list: list[str] | None = (
        [s.strip() for s in feature_subset.split(",") if s.strip()] if feature_subset else None
    )
    run_id = run_backtest(
        con,
        league,
        train_min_seasons=train_min_seasons,
        step_days=step_days,
        model_version=model_version,
        xi_decay=xi_decay,
        xg_skellam_run_id=xg_skellam_run_id,
        feature_subset=subset_list,
    )
    row = con.execute(
        "SELECT status, n_folds, n_predictions FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    assert row is not None, f"backtest_runs row missing for run_id={run_id}"
    typer.echo(f"run_id={run_id} status={row[0]} n_folds={row[1]} n_predictions={row[2]}")


if __name__ == "__main__":
    app()
