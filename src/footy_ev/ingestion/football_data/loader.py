"""Load football-data.co.uk season CSVs into DuckDB with upsert + drift detection.

TODO(schema-drift-review): ``schema_drift_log`` rows with ``resolved = FALSE`` are
technical debt. Each unresolved row represents a source column we saw but never
promoted into the typed schema. Review cadence for clearing this queue is NOT
implemented yet — this comment is the placeholder. Open a review job (manual or
automated) before the drift log grows beyond ~20 unresolved columns, or the
registry will silently diverge from upstream reality.

Accounting invariant: ``LoadReport.total() == inserted + updated + unchanged + rejected``.
The ``test_load_identical_second_run_reports_zero_updates`` unit test is the canary
for the hash-based unchanged detection — if it goes red, the upsert logic has drifted.

CSV reading strategy:
    1. Fast path — Polars (``infer_schema_length=0`` to keep all cells as strings).
    2. Fallback — stdlib ``csv.reader`` on ``polars.exceptions.ComputeError``, which
       Polars raises when row field counts disagree with the header. The fallback
       captures the overflow into synthetic keys ``_overflow_pos_<N>`` (N is the
       0-indexed absolute position in the source row), so they flow through the
       existing ``extras`` MAP unchanged. A single ``<HEADER_OVERFLOW>`` summary
       row is written to ``schema_drift_log`` recording the distinct row widths
       observed across the season — e.g. ``['57', '62', '72']`` for a season with
       two staged column additions mid-year.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
from polars.exceptions import ComputeError
from pydantic import ValidationError

from footy_ev.ingestion.football_data.columns import (
    REGISTRY,
    REQUIRED_SOURCE_NAMES,
    SOURCE_NAMES,
)
from footy_ev.ingestion.football_data.parse import FootballDataRow
from footy_ev.ingestion.football_data.source import build_url, league_to_source_code


class SchemaDriftError(Exception):
    """Raised when a required source column is missing from a CSV header."""


@dataclass(frozen=True, slots=True)
class LoadReport:
    """Accounting for one ``load_season`` invocation.

    Invariant: ``total() == inserted + updated + unchanged + rejected``.
    """

    inserted: int
    updated: int
    unchanged: int
    rejected: int
    missing_required: list[str] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)

    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged + self.rejected


_METADATA_COLS: tuple[str, ...] = (
    "league",
    "season",
    "source_code",
    "source_url",
    "ingested_at",
    "source_row_hash",
)
_TYPED_COLS: tuple[str, ...] = tuple(c.canonical_name for c in REGISTRY)
_ALL_COLS: tuple[str, ...] = (*_METADATA_COLS, *_TYPED_COLS, "extras")
_PK_COLS: frozenset[str] = frozenset({"league", "season", "match_date", "home_team", "away_team"})

# Sentinel used in schema_drift_log when at least one data row has more fields
# than the CSV header declares.
_HEADER_OVERFLOW_MARKER: str = "<HEADER_OVERFLOW>"


# --------------------------------------------------------------------------- #
# CSV reading
# --------------------------------------------------------------------------- #
def _read_rows_polars(
    csv_path: Path,
) -> tuple[list[dict[str, Any]], list[str], list[int]]:
    """Fast path: Polars CSV reader. Raises ``ComputeError`` on ragged rows."""
    df = pl.read_csv(csv_path, infer_schema_length=0)
    rows = list(df.iter_rows(named=True))
    return rows, list(df.columns), [len(df.columns)]


def _read_rows_lenient(
    csv_path: Path,
) -> tuple[list[dict[str, Any]], list[str], list[int]]:
    """Lenient path: stdlib ``csv.reader``; tolerates ragged rows.

    Rows with more fields than the header gain extra keys named
    ``_overflow_pos_<N>`` where ``N`` is the 0-indexed absolute field position in
    the source row (so a header of width 57 yields overflow keys
    ``_overflow_pos_57``, ``_overflow_pos_58``, ...). Rows shorter than the header
    are passed through with missing keys; pydantic's null-string validator coerces
    them to ``None`` like any other empty cell.

    Returns:
        ``(rows, header_columns, sorted_distinct_field_counts)``. The third item
        is used by the drift-log writer to record the set of row widths observed
        across the season.
    """
    rows: list[dict[str, Any]] = []
    field_counts: set[int] = set()
    # errors="replace" guards against rare non-UTF-8 bytes in pre-2010 archives.
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return [], [], []
        header_len = len(header)
        for raw_list in reader:
            if not raw_list:  # skip incidental blank lines defensively
                continue
            field_counts.add(len(raw_list))
            row: dict[str, Any] = {}
            for i, value in enumerate(raw_list):
                if i < header_len:
                    row[header[i]] = value
                else:
                    row[f"_overflow_pos_{i}"] = value
            rows.append(row)
    return rows, header, sorted(field_counts)


def _read_rows(
    csv_path: Path,
) -> tuple[list[dict[str, Any]], list[str], list[int]]:
    """Try Polars first; fall back to the lenient stdlib reader on ragged rows."""
    try:
        return _read_rows_polars(csv_path)
    except ComputeError:
        return _read_rows_lenient(csv_path)


# --------------------------------------------------------------------------- #
# Hashing + record assembly
# --------------------------------------------------------------------------- #
def _hash_parsed(parsed: FootballDataRow) -> str:
    """Stable sha256 over the parsed row including extras. Order-independent."""
    data = parsed.model_dump(mode="json", by_alias=False)
    if parsed.__pydantic_extra__:
        data["__extras__"] = {str(k): v for k, v in parsed.__pydantic_extra__.items()}
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_for_row(
    *,
    parsed: FootballDataRow,
    league: str,
    season: str,
    source_code: str,
    source_url: str,
    ingested_at: datetime,
    row_hash: str,
) -> tuple[Any, ...]:
    """Flatten a parsed row + metadata into the ordered tuple ``_ALL_COLS`` expects."""
    extras_raw = parsed.__pydantic_extra__ or {}
    extras = {str(k): ("" if v is None else str(v)) for k, v in extras_raw.items()}

    metadata: list[Any] = [league, season, source_code, source_url, ingested_at, row_hash]
    typed_values: list[Any] = [getattr(parsed, col) for col in _TYPED_COLS]
    return (*metadata, *typed_values, extras)


# --------------------------------------------------------------------------- #
# Drift logging
# --------------------------------------------------------------------------- #
def _sample_values_for_column(rows: list[dict[str, Any]], column: str, limit: int = 3) -> list[str]:
    samples: list[str] = []
    for row in rows:
        v = row.get(column)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        samples.append(s)
        if len(samples) >= limit:
            break
    return samples


def _log_unknown_columns(
    con: duckdb.DuckDBPyConnection,
    *,
    league: str,
    season: str,
    source_code: str,
    unknown: set[str],
    rows: list[dict[str, Any]],
    now: datetime,
) -> None:
    """Insert one row per unknown header column into ``schema_drift_log``."""
    if not unknown:
        return
    for col in sorted(unknown):
        samples = _sample_values_for_column(rows, col)
        con.execute(
            """
            INSERT INTO schema_drift_log
                (observed_at, league, season, source_code, column_name, sample_values, resolved)
            VALUES (?, ?, ?, ?, ?, ?, FALSE)
            """,
            [now, league, season, source_code, col, samples],
        )


def _log_header_overflow(
    con: duckdb.DuckDBPyConnection,
    *,
    league: str,
    season: str,
    source_code: str,
    distinct_field_counts: list[int],
    now: datetime,
) -> None:
    """Insert a summary ``<HEADER_OVERFLOW>`` row recording all row widths seen."""
    sample_values = [str(fc) for fc in sorted(distinct_field_counts)]
    con.execute(
        """
        INSERT INTO schema_drift_log
            (observed_at, league, season, source_code, column_name, sample_values, resolved)
        VALUES (?, ?, ?, ?, ?, ?, FALSE)
        """,
        [now, league, season, source_code, _HEADER_OVERFLOW_MARKER, sample_values],
    )


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #
def _existing_hashes(
    con: duckdb.DuckDBPyConnection,
    league: str,
    season: str,
) -> dict[tuple[Any, Any, Any], str]:
    rows = con.execute(
        """
        SELECT match_date, home_team, away_team, source_row_hash
        FROM raw_match_results
        WHERE league = ? AND season = ?
        """,
        [league, season],
    ).fetchall()
    return {(r[0], r[1], r[2]): r[3] for r in rows}


def _bulk_write(
    con: duckdb.DuckDBPyConnection,
    records: list[tuple[Any, ...]],
    *,
    upsert: bool,
) -> None:
    if not records:
        return
    col_list = ", ".join(_ALL_COLS)
    placeholders = ", ".join(["?"] * len(_ALL_COLS))
    if upsert:
        update_set = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in _ALL_COLS if col not in _PK_COLS
        )
        sql = (
            f"INSERT INTO raw_match_results ({col_list}) VALUES ({placeholders})"
            f" ON CONFLICT (league, season, match_date, home_team, away_team)"
            f" DO UPDATE SET {update_set}"
        )
    else:
        sql = f"INSERT INTO raw_match_results ({col_list}) VALUES ({placeholders})"
    con.executemany(sql, records)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def load_season(
    *,
    league: str,
    season: str,
    csv_path: Path,
    con: duckdb.DuckDBPyConnection,
    source_url: str | None = None,
    now: datetime | None = None,
) -> LoadReport:
    """Read a football-data.co.uk CSV and upsert rows into ``raw_match_results``.

    Raises:
        SchemaDriftError: If any REQUIRED source column is missing from the CSV header.
            The database is not mutated when this is raised.
    """
    now = now or datetime.now(UTC)
    source_code = league_to_source_code(league)
    url = source_url or build_url(league, season)

    rows_data, header_list, field_counts = _read_rows(csv_path)
    header = set(header_list)
    header_len = len(header_list)

    missing = REQUIRED_SOURCE_NAMES - header
    if missing:
        raise SchemaDriftError(
            f"missing required source columns for {league} {season}: {sorted(missing)}"
        )
    unknown = header - SOURCE_NAMES

    _log_unknown_columns(
        con,
        league=league,
        season=season,
        source_code=source_code,
        unknown=unknown,
        rows=rows_data,
        now=now,
    )

    if field_counts and max(field_counts) > header_len:
        _log_header_overflow(
            con,
            league=league,
            season=season,
            source_code=source_code,
            distinct_field_counts=field_counts,
            now=now,
        )

    existing = _existing_hashes(con, league, season)

    inserted_records: list[tuple[Any, ...]] = []
    updated_records: list[tuple[Any, ...]] = []
    unchanged = 0
    rejected = 0

    for raw_row in rows_data:
        try:
            parsed = FootballDataRow.model_validate(raw_row)
        except ValidationError:
            rejected += 1
            continue

        row_hash = _hash_parsed(parsed)
        pk = (parsed.match_date, parsed.home_team, parsed.away_team)
        prior_hash = existing.get(pk)

        record = _record_for_row(
            parsed=parsed,
            league=league,
            season=season,
            source_code=source_code,
            source_url=url,
            ingested_at=now,
            row_hash=row_hash,
        )

        if prior_hash is None:
            inserted_records.append(record)
        elif prior_hash == row_hash:
            unchanged += 1
        else:
            updated_records.append(record)

    _bulk_write(con, inserted_records, upsert=False)
    _bulk_write(con, updated_records, upsert=True)

    return LoadReport(
        inserted=len(inserted_records),
        updated=len(updated_records),
        unchanged=unchanged,
        rejected=rejected,
        missing_required=[],
        unknown_columns=sorted(unknown),
    )


if __name__ == "__main__":
    from footy_ev.db import apply_migrations

    con = duckdb.connect(":memory:")
    apply_migrations(con)
    fixture = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "football_data"
        / "E0_sample.csv"
    )
    report = load_season(league="EPL", season="2024-2025", csv_path=fixture, con=con)
    print(f"report: {report}")
    print(f"invariant: total={report.total()}")
