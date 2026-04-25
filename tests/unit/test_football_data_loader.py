"""Unit tests for football_data/loader.py."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from footy_ev.db import apply_migrations
from footy_ev.ingestion.football_data.loader import (
    LoadReport,
    SchemaDriftError,
    load_season,
)

FIXTURE_CSV = (
    Path(__file__).resolve().parent.parent / "fixtures" / "football_data" / "E0_sample.csv"
)
FIXTURE_ROWS = 6


@pytest.fixture  # type: ignore[misc]
def db_con() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    yield con
    con.close()


def _write_csv(dst: Path, text: str) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    return dst


def _fixture_text() -> str:
    return FIXTURE_CSV.read_text(encoding="utf-8")


def _row_count(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM raw_match_results").fetchone()[0])


def test_load_fresh_inserts_all(db_con: duckdb.DuckDBPyConnection) -> None:
    report = load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)
    assert report.inserted == FIXTURE_ROWS
    assert report.updated == 0
    assert report.unchanged == 0
    assert report.rejected == 0
    assert _row_count(db_con) == FIXTURE_ROWS


def test_load_identical_second_run_reports_zero_updates(
    db_con: duckdb.DuckDBPyConnection,
) -> None:
    """Canary test per tightening ask A.

    If this goes red, the hash-based unchanged detection has drifted: idempotency
    is broken and we'd be rewriting untouched rows on every re-ingestion.
    """
    first = load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)
    second = load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)
    assert first.inserted == FIXTURE_ROWS
    assert second.inserted == 0
    assert second.updated == 0
    assert second.unchanged == FIXTURE_ROWS
    assert second.rejected == 0


def test_load_update_on_hash_change(db_con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)

    mutated_text = _fixture_text().replace(
        "E0,16/08/2024,20:00,Man United,Fulham,1,0,H",
        "E0,16/08/2024,20:00,Man United,Fulham,2,0,H",
    )
    mutated_csv = _write_csv(tmp_path / "mutated.csv", mutated_text)

    report = load_season(league="EPL", season="2024-2025", csv_path=mutated_csv, con=db_con)
    assert report.inserted == 0
    assert report.updated == 1
    assert report.unchanged == FIXTURE_ROWS - 1
    assert report.rejected == 0

    fthg = db_con.execute(
        "SELECT fthg FROM raw_match_results WHERE home_team = 'Man United' AND match_date = '2024-08-16'"
    ).fetchone()
    assert fthg == (2,)


def test_load_rejects_malformed_row(db_con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    bad_text = _fixture_text().replace(
        "E0,16/08/2024,20:00,Man United,Fulham,1,0,H",
        "E0,16/08/2024,20:00,Man United,Fulham,not_an_int,0,H",
    )
    bad_csv = _write_csv(tmp_path / "bad.csv", bad_text)

    report = load_season(league="EPL", season="2024-2025", csv_path=bad_csv, con=db_con)
    assert report.rejected == 1
    assert report.inserted == FIXTURE_ROWS - 1
    assert _row_count(db_con) == FIXTURE_ROWS - 1


def test_load_missing_required_raises_drift(
    db_con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    text = _fixture_text()
    # Strip FTHG column from header AND every row. FTHG is column index 5.
    lines = text.strip().split("\n")
    stripped = "\n".join(
        ",".join(c for i, c in enumerate(line.split(",")) if i != 5) for line in lines
    )
    csv = _write_csv(tmp_path / "no_fthg.csv", stripped + "\n")

    with pytest.raises(SchemaDriftError):
        load_season(league="EPL", season="2024-2025", csv_path=csv, con=db_con)

    assert _row_count(db_con) == 0


def test_load_unknown_column_flows_to_extras_and_drift_log(
    db_con: duckdb.DuckDBPyConnection,
) -> None:
    """The fixture's ``Foo`` column is unknown → drift log entry + value in extras."""
    load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)

    drift_rows = db_con.execute(
        "SELECT column_name, resolved FROM schema_drift_log WHERE column_name = 'Foo'"
    ).fetchall()
    assert drift_rows == [("Foo", False)]

    extras_val = db_con.execute(
        "SELECT extras['Foo'] FROM raw_match_results WHERE home_team = 'Man United'"
    ).fetchone()
    assert extras_val == (["bar1"],) or extras_val == ("bar1",)


def test_load_report_accounting_invariant(
    db_con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """inserted + updated + unchanged + rejected must equal total rows processed."""
    bad_text = _fixture_text().replace(
        "E0,18/08/2024,14:00,Nott'm Forest,Bournemouth,1,1,D",
        "E0,18/08/2024,14:00,Nott'm Forest,Bournemouth,not_an_int,1,D",
    )
    bad_csv = _write_csv(tmp_path / "bad.csv", bad_text)

    r1 = load_season(league="EPL", season="2024-2025", csv_path=bad_csv, con=db_con)
    assert r1.total() == FIXTURE_ROWS

    r2 = load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)
    assert r2.total() == FIXTURE_ROWS
    # Second run on clean CSV should insert the previously-rejected row and leave
    # the rest unchanged.
    assert r2.inserted == 1
    assert r2.updated == 0
    assert r2.unchanged == FIXTURE_ROWS - 1
    assert r2.rejected == 0


def test_load_report_is_frozen_dataclass() -> None:
    r = LoadReport(inserted=1, updated=0, unchanged=0, rejected=0)
    with pytest.raises((AttributeError, TypeError)):
        r.inserted = 99


# --------------------------------------------------------------------------- #
# Ragged-CSV handling (Polars fast path -> stdlib csv fallback).
# --------------------------------------------------------------------------- #
RAGGED_CSV = (
    Path(__file__).resolve().parent.parent / "fixtures" / "football_data" / "ragged_sample.csv"
)


def test_loader_handles_ragged_rows(
    db_con: duckdb.DuckDBPyConnection,
) -> None:
    """Header has 7 cols; rows have widths 7, 9, 10. All three should load.

    Overflow values land in ``extras`` under positional keys
    ``_overflow_pos_<N>`` (N = 0-indexed absolute position). One drift-log row
    with column_name ``<HEADER_OVERFLOW>`` records the distinct widths seen.
    """
    report = load_season(league="EPL", season="2024-2025", csv_path=RAGGED_CSV, con=db_con)
    assert report.inserted == 3
    assert report.updated == 0
    assert report.unchanged == 0
    assert report.rejected == 0

    # 1) Overflow values land in extras with positional keys.
    liverpool_extras = db_con.execute(
        "SELECT extras FROM raw_match_results WHERE home_team = 'Liverpool'"
    ).fetchone()
    assert liverpool_extras is not None
    extras_map = liverpool_extras[0]
    assert extras_map.get("_overflow_pos_7") == "extra1"
    assert extras_map.get("_overflow_pos_8") == "extra2"
    assert "_overflow_pos_9" not in extras_map  # Liverpool row had width 9

    city_extras = db_con.execute(
        "SELECT extras FROM raw_match_results WHERE home_team = 'City'"
    ).fetchone()
    assert city_extras is not None
    city_map = city_extras[0]
    assert city_map.get("_overflow_pos_7") == "extra3"
    assert city_map.get("_overflow_pos_8") == "extra4"
    assert city_map.get("_overflow_pos_9") == "extra5"

    arsenal_extras = db_con.execute(
        "SELECT extras FROM raw_match_results WHERE home_team = 'Arsenal'"
    ).fetchone()
    assert arsenal_extras is not None
    # Clean row — no overflow keys should be present.
    assert not any(k.startswith("_overflow_pos_") for k in arsenal_extras[0])

    # 2) Schema drift log records the SET of distinct widths.
    overflow_rows = db_con.execute(
        """
        SELECT sample_values
        FROM schema_drift_log
        WHERE column_name = '<HEADER_OVERFLOW>' AND season = '2024-2025'
        """
    ).fetchall()
    assert len(overflow_rows) == 1
    sample_values = overflow_rows[0][0]
    assert sorted(sample_values) == ["10", "7", "9"]


def test_loader_extras_keys_unique(db_con: duckdb.DuckDBPyConnection) -> None:
    """Invariant: every extras MAP has unique keys per row.

    Migration 002 trusts this — when copying ``extras['SourceName'][1]`` (first
    list element) to a typed column, it assumes only one value per key. Python
    dict semantics give us this for free at write time, but if a future loader
    bug ever produced duplicate keys (e.g., case-collisions, source-rename
    handling), this test catches the regression before migration code blindly
    reads ``[1]`` and silently drops the rest.
    """
    load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)

    duplicates = db_con.execute(
        """
        SELECT COUNT(*) FROM raw_match_results
        WHERE LEN(map_keys(extras)) <> LEN(list_distinct(map_keys(extras)))
        """
    ).fetchone()
    assert duplicates is not None
    assert duplicates[0] == 0, f"{duplicates[0]} rows have duplicate extras keys"


def test_loader_clean_csv_uses_polars_path(
    db_con: duckdb.DuckDBPyConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean CSV must NOT trip the lenient fallback."""

    def _boom(*_a: object, **_kw: object) -> object:
        raise AssertionError("lenient fallback should not be called for clean CSVs")

    monkeypatch.setattr("footy_ev.ingestion.football_data.loader._read_rows_lenient", _boom)

    report = load_season(league="EPL", season="2024-2025", csv_path=FIXTURE_CSV, con=db_con)
    assert report.inserted == FIXTURE_ROWS

    # Clean files must NOT write a <HEADER_OVERFLOW> drift row.
    overflow_count = db_con.execute(
        "SELECT COUNT(*) FROM schema_drift_log WHERE column_name = '<HEADER_OVERFLOW>'"
    ).fetchone()[0]
    assert overflow_count == 0
