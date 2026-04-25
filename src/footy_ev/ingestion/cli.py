r"""Typer CLI for ingestion commands.

Invocation:
    uv run python -m footy_ev.ingestion.cli ingest-season --league EPL --season 2024-2025
    uv run python -m footy_ev.ingestion.cli ingest-league --league EPL --from-season 2000-2001
    uv run python -m footy_ev.ingestion.cli all

The ``.\make.ps1`` wrapper forwards its named parameters into these commands.
"""

from __future__ import annotations

import random
import time
from datetime import date
from pathlib import Path

import duckdb
import httpx
import typer

from footy_ev.db import apply_migrations
from footy_ev.ingestion.football_data.loader import LoadReport, load_season
from footy_ev.ingestion.football_data.source import fetch_season

app = typer.Typer(add_completion=False, help="footy-ev ingestion commands.")

DEFAULT_RAW_DIR = Path("data/raw/football_data")
DEFAULT_DB_PATH = Path("data/warehouse/footy_ev.duckdb")


def current_season(today: date | None = None) -> str:
    """Return the season string containing ``today``.

    European football seasons roll in August. August onward: this year/next year.
    January–July: previous year/this year.
    """
    t = today or date.today()
    if t.month >= 8:
        return f"{t.year}-{t.year + 1}"
    return f"{t.year - 1}-{t.year}"


def season_range(from_season: str, to_season: str) -> list[str]:
    """Return every ``YYYY-YYYY`` season from ``from_season`` to ``to_season`` inclusive."""
    y1 = int(from_season[:4])
    y2 = int(to_season[:4])
    if y2 < y1:
        raise ValueError(f"to-season {to_season!r} precedes from-season {from_season!r}")
    return [f"{y}-{y + 1}" for y in range(y1, y2 + 1)]


def _politeness_sleep() -> None:
    time.sleep(3 + random.uniform(0, 2))


def _open_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    return con


def _format_report(league: str, season: str, report: LoadReport) -> str:
    return (
        f"[{league} {season}] "
        f"inserted={report.inserted} updated={report.updated} "
        f"unchanged={report.unchanged} rejected={report.rejected} "
        f"unknown_cols={len(report.unknown_columns)}"
    )


def _do_ingest_league(
    *,
    league: str,
    from_season: str,
    to_season: str | None,
    refresh: bool,
    raw_dir: Path,
    db_path: Path,
) -> None:
    end = to_season or current_season()
    seasons = season_range(from_season, end)
    con = _open_db(db_path)
    try:
        for i, s in enumerate(seasons):
            try:
                csv_path = fetch_season(league, s, raw_dir=raw_dir, refresh=refresh)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    typer.echo(f"[{league} {s}] 404 (season not available); skipping")
                    continue
                raise
            report = load_season(league=league, season=s, csv_path=csv_path, con=con)
            typer.echo(_format_report(league, s, report))
            if i < len(seasons) - 1:
                _politeness_sleep()
    finally:
        con.close()


@app.command("ingest-season")  # type: ignore[misc]
def ingest_season(
    league: str = typer.Option(..., "--league"),
    season: str = typer.Option(..., "--season"),
    refresh: bool = typer.Option(False, "--refresh"),
    raw_dir: Path = typer.Option(DEFAULT_RAW_DIR, "--raw-dir"),  # noqa: B008
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db"),  # noqa: B008
) -> None:
    """Fetch + load one (league, season) into DuckDB."""
    con = _open_db(db_path)
    try:
        csv_path = fetch_season(league, season, raw_dir=raw_dir, refresh=refresh)
        report = load_season(league=league, season=season, csv_path=csv_path, con=con)
        typer.echo(_format_report(league, season, report))
    finally:
        con.close()


@app.command("ingest-league")  # type: ignore[misc]
def ingest_league(
    league: str = typer.Option(..., "--league"),
    from_season: str = typer.Option("2000-2001", "--from-season"),
    to_season: str = typer.Option(None, "--to-season"),
    refresh: bool = typer.Option(False, "--refresh"),
    raw_dir: Path = typer.Option(DEFAULT_RAW_DIR, "--raw-dir"),  # noqa: B008
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db"),  # noqa: B008
) -> None:
    """Loop over all seasons in a range with 3-5s jittered politeness sleep between each."""
    _do_ingest_league(
        league=league,
        from_season=from_season,
        to_season=to_season,
        refresh=refresh,
        raw_dir=raw_dir,
        db_path=db_path,
    )


@app.command("all")  # type: ignore[misc]
def all_() -> None:
    """Alias for ``ingest-league --league EPL --from-season 2000-2001``."""
    _do_ingest_league(
        league="EPL",
        from_season="2000-2001",
        to_season=None,
        refresh=False,
        raw_dir=DEFAULT_RAW_DIR,
        db_path=DEFAULT_DB_PATH,
    )


if __name__ == "__main__":
    app()
