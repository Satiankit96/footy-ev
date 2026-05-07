"""Load Understat per-match xG records into DuckDB with upsert + drift detection.

Mirrors ``ingestion/football_data/loader.py`` patterns:
  - sha256 row hash short-circuits no-op upserts.
  - Unknown sibling keys (captured by Pydantic's ``extra="allow"``) flow into
    the ``extras`` MAP and a ``schema_drift_log`` row is emitted with
    ``source_code = 'understat'``.
  - Accounting invariant: ``UnderstatLoadReport.total() ==
    inserted + updated + unchanged + rejected``.

UPSERT statement (per R2):
    INSERT INTO raw_understat_matches (...) VALUES (...)
    ON CONFLICT (understat_match_id) DO UPDATE SET ...

The conflict target is named explicitly so a future composite UNIQUE tripwire
(Option C: UNIQUE (league, season, kickoff_utc, home_team_raw, away_team_raw))
does not change which constraint the upsert resolves against.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
from pydantic import ValidationError

from footy_ev.ingestion.understat.parse import UnderstatMatchRecord, parse_payload
from footy_ev.ingestion.understat.source import build_url


@dataclass(frozen=True, slots=True)
class UnderstatLoadReport:
    """Accounting for one ``load_season`` invocation.

    Invariant: ``total() == inserted + updated + unchanged + rejected``.
    """

    inserted: int
    updated: int
    unchanged: int
    rejected: int
    unknown_keys: list[str] = field(default_factory=list)

    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged + self.rejected


_SOURCE_CODE: str = "understat"

_METADATA_COLS: tuple[str, ...] = (
    "league",
    "season",
    "source_code",
    "source_url",
    "ingested_at",
    "source_row_hash",
)
_TYPED_COLS: tuple[str, ...] = (
    "understat_match_id",
    "understat_home_id",
    "understat_away_id",
    "home_team_raw",
    "away_team_raw",
    "kickoff_local",
    "kickoff_utc",
    "is_result",
    "home_goals",
    "away_goals",
    "home_xg",
    "away_xg",
    "forecast_home_pct",
    "forecast_draw_pct",
    "forecast_away_pct",
)
_ALL_COLS: tuple[str, ...] = (*_METADATA_COLS, *_TYPED_COLS, "extras")
_PK_COL: str = "understat_match_id"


# --------------------------------------------------------------------------- #
# Hashing + record assembly
# --------------------------------------------------------------------------- #
def hash_record(record: UnderstatMatchRecord) -> str:
    """Stable sha256 over the parsed record including ``__pydantic_extra__``.

    Order-independent across runs — same record fields produce the same hash
    regardless of dict insertion order. Used by ``load_season`` to short-circuit
    upserts on unchanged matches.
    """
    data = record.model_dump(mode="json", by_alias=False)
    if record.__pydantic_extra__:
        data["__extras__"] = {str(k): v for k, v in record.__pydantic_extra__.items()}
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_for_row(
    *,
    parsed: UnderstatMatchRecord,
    league: str,
    season: str,
    source_url: str,
    ingested_at: datetime,
    row_hash: str,
) -> tuple[Any, ...]:
    """Flatten a parsed record + metadata into the ordered tuple ``_ALL_COLS`` expects."""
    extras_raw = parsed.__pydantic_extra__ or {}
    extras = {str(k): ("" if v is None else str(v)) for k, v in extras_raw.items()}

    metadata: list[Any] = [league, season, _SOURCE_CODE, source_url, ingested_at, row_hash]
    typed_values: list[Any] = [getattr(parsed, col) for col in _TYPED_COLS]
    return (*metadata, *typed_values, extras)


# --------------------------------------------------------------------------- #
# Drift logging
# --------------------------------------------------------------------------- #
def _collect_unknown_keys(
    records: list[UnderstatMatchRecord],
) -> tuple[list[str], dict[str, list[str]]]:
    keys: set[str] = set()
    samples: dict[str, list[str]] = {}
    for r in records:
        if not r.__pydantic_extra__:
            continue
        for k, v in r.__pydantic_extra__.items():
            keys.add(k)
            bucket = samples.setdefault(k, [])
            if len(bucket) < 3:
                bucket.append(str(v))
    return sorted(keys), samples


def _log_unknown_keys(
    con: duckdb.DuckDBPyConnection,
    *,
    league: str,
    season: str,
    unknowns: list[str],
    samples: dict[str, list[str]],
    now: datetime,
) -> None:
    for k in unknowns:
        con.execute(
            """
            INSERT INTO schema_drift_log
                (observed_at, league, season, source_code, column_name, sample_values, resolved)
            VALUES (?, ?, ?, ?, ?, ?, FALSE)
            """,
            [now, league, season, _SOURCE_CODE, k, samples.get(k, [])],
        )


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #
def _existing_hashes(
    con: duckdb.DuckDBPyConnection,
    league: str,
    season: str,
) -> dict[str, str]:
    rows = con.execute(
        """
        SELECT understat_match_id, source_row_hash
        FROM raw_understat_matches
        WHERE league = ? AND season = ?
        """,
        [league, season],
    ).fetchall()
    return {r[0]: r[1] for r in rows}


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
        update_set = ", ".join(f"{col} = EXCLUDED.{col}" for col in _ALL_COLS if col != _PK_COL)
        sql = (
            f"INSERT INTO raw_understat_matches ({col_list}) VALUES ({placeholders})"
            f" ON CONFLICT ({_PK_COL}) DO UPDATE SET {update_set}"
        )
    else:
        sql = f"INSERT INTO raw_understat_matches ({col_list}) VALUES ({placeholders})"
    con.executemany(sql, records)


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def load_season(
    *,
    league: str,
    season: str,
    json_path: Path,
    con: duckdb.DuckDBPyConnection,
    source_url: str | None = None,
    now: datetime | None = None,
) -> UnderstatLoadReport:
    """Read an Understat AJAX JSON cache file and upsert matches into ``raw_understat_matches``.

    Args:
        league: Canonical league code (e.g. ``"EPL"``).
        season: Human season string like ``"2024-2025"``.
        json_path: Path to the cached JSON file (from ``source.fetch_season``).
        con: Open DuckDB connection. Migrations 001-003 must already be applied.
        source_url: Optional override for the ``source_url`` column. Defaults to
            the canonical URL derived from (league, season).
        now: Optional override for the ``ingested_at`` timestamp (UTC).

    Returns:
        ``UnderstatLoadReport`` summarizing the load.

    Raises:
        UnderstatParseError: If the cached JSON doesn't contain the expected
            shape. Database is not mutated when this is raised.
    """
    now = now or datetime.now(UTC)
    url = source_url or build_url(league, season)

    text = json_path.read_text(encoding="utf-8")
    records = parse_payload(text, season=season, league=league)

    existing = _existing_hashes(con, league, season)

    inserted_records: list[tuple[Any, ...]] = []
    updated_records: list[tuple[Any, ...]] = []
    unchanged = 0
    rejected = 0

    for parsed in records:
        try:
            row_hash = hash_record(parsed)
        except (TypeError, ValidationError):
            rejected += 1
            continue

        record = _record_for_row(
            parsed=parsed,
            league=league,
            season=season,
            source_url=url,
            ingested_at=now,
            row_hash=row_hash,
        )

        prior_hash = existing.get(parsed.understat_match_id)
        if prior_hash is None:
            inserted_records.append(record)
        elif prior_hash == row_hash:
            unchanged += 1
        else:
            updated_records.append(record)

    _bulk_write(con, inserted_records, upsert=False)
    _bulk_write(con, updated_records, upsert=True)

    unknowns, samples = _collect_unknown_keys(records)
    _log_unknown_keys(
        con,
        league=league,
        season=season,
        unknowns=unknowns,
        samples=samples,
        now=now,
    )

    return UnderstatLoadReport(
        inserted=len(inserted_records),
        updated=len(updated_records),
        unchanged=unchanged,
        rejected=rejected,
        unknown_keys=unknowns,
    )


def detect_unmapped_teams(
    *,
    league: str,
    con: duckdb.DuckDBPyConnection,
) -> list[str]:
    """Return raw Understat team names with no matching ``team_aliases`` row.

    Used by the ``understat-detect-unmapped`` CLI to surface entity-resolution
    drift after each ingest. Returns sorted, deduplicated raw names that appear
    in either the home or away column of ``raw_understat_matches`` for the
    given league but lack a corresponding ``team_aliases`` row with
    ``source = 'understat'``.

    Args:
        league: Canonical league code to filter on.
        con: Open DuckDB connection.

    Returns:
        Sorted list of unmapped raw team names. Empty list means every raw name
        in ``raw_understat_matches`` for this league is mapped.
    """
    rows = con.execute(
        """
        WITH raw_names AS (
            SELECT DISTINCT home_team_raw AS name FROM raw_understat_matches WHERE league = ?
            UNION
            SELECT DISTINCT away_team_raw AS name FROM raw_understat_matches WHERE league = ?
        )
        SELECT rn.name
        FROM raw_names rn
        LEFT JOIN team_aliases ta
          ON ta.source = 'understat' AND ta.raw_name = rn.name
        WHERE ta.team_id IS NULL
        ORDER BY rn.name
        """,
        [league, league],
    ).fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    from footy_ev.db import apply_migrations

    con = duckdb.connect(":memory:")
    apply_migrations(con)
    fixture = (
        Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "understat" / "EPL_2023.json"
    )
    report = load_season(league="EPL", season="2023-2024", json_path=fixture, con=con)
    print(f"report: {report}")
    print(f"invariant: total={report.total()}")
