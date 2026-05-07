"""Integration test for migration 002 against the real warehouse DB.

Gated on the warehouse file existing (skipped on a fresh checkout). After
migration 002 has run + the loader has refreshed hashes, this test verifies
the post-migration state of ``raw_match_results``.

Note on f-string SQL: column names interpolated below come from a hardcoded
allowlist derived from ``REGISTRY`` at compile time. CLAUDE.md's "no f-string
SQL" rule targets injection from untrusted input — these are whitelisted.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from footy_ev.ingestion.football_data.columns import BY_SOURCE

WAREHOUSE_DB = Path("data/warehouse/footy_ev.duckdb")

# The 52 promoted source names from migration 002.
_PROMOTED_SOURCE_NAMES: tuple[str, ...] = (
    "B365CH",
    "B365CD",
    "B365CA",
    "BWCH",
    "BWCD",
    "BWCA",
    "WHCH",
    "WHCD",
    "WHCA",
    "PSCH",
    "PSCD",
    "PSCA",
    "IWCH",
    "IWCD",
    "IWCA",
    "VCCH",
    "VCCD",
    "VCCA",
    "MaxCH",
    "MaxCD",
    "MaxCA",
    "AvgCH",
    "AvgCD",
    "AvgCA",
    "BFECH",
    "BFECD",
    "BFECA",
    "B365C>2.5",
    "B365C<2.5",
    "MaxC>2.5",
    "MaxC<2.5",
    "AvgC>2.5",
    "AvgC<2.5",
    "PC>2.5",
    "PC<2.5",
    "BFEC>2.5",
    "BFEC<2.5",
    "AHCh",
    "B365CAHH",
    "B365CAHA",
    "MaxCAHH",
    "MaxCAHA",
    "AvgCAHH",
    "AvgCAHA",
    "PCAHH",
    "PCAHA",
    "BFECAHH",
    "BFECAHA",
    "MaxAHH",
    "MaxAHA",
    "AvgAHH",
    "AvgAHA",
)

# Derived canonical column names (whitelist for f-string SQL below).
_PROMOTED_CANONICAL: tuple[str, ...] = tuple(
    BY_SOURCE[s].canonical_name for s in _PROMOTED_SOURCE_NAMES
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not WAREHOUSE_DB.exists(),
        reason=f"warehouse DB {WAREHOUSE_DB} not present; run backfill first",
    ),
]


def test_no_promoted_keys_remain_in_extras() -> None:
    """Phase C must have removed every promoted key from every row's extras."""
    con = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    try:
        leftovers: list[tuple[str, int]] = []
        for src in _PROMOTED_SOURCE_NAMES:
            count = con.execute(
                "SELECT COUNT(*) FROM raw_match_results WHERE list_contains(map_keys(extras), ?)",
                [src],
            ).fetchone()[0]
            if count > 0:
                leftovers.append((src, count))
        assert not leftovers, f"promoted keys still in extras: {leftovers}"
    finally:
        con.close()


def test_promoted_columns_have_data() -> None:
    """Every promoted column must have at least one non-null value.

    A column with zero non-null after migration means either (a) the column
    never appeared in any season (contradicting the drift report), or (b)
    extraction failed — either way, halt for investigation.
    """
    con = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    try:
        zero_cols: list[str] = []
        for canonical in _PROMOTED_CANONICAL:
            assert canonical in set(_PROMOTED_CANONICAL)  # whitelist gate
            count = con.execute(
                f"SELECT COUNT(*) FROM raw_match_results WHERE {canonical} IS NOT NULL"  # noqa: S608
            ).fetchone()[0]
            if count == 0:
                zero_cols.append(canonical)
        assert not zero_cols, f"promoted columns with zero non-null values: {zero_cols}"
    finally:
        con.close()


def test_pinnacle_closing_has_at_least_13_seasons() -> None:
    """PSCH (Pinnacle 1X2 closing) is the 14-season CLV training label.

    Slack: in-progress 2025-26 may not yet have closing odds populated; we
    expect 13 or 14 seasons of coverage.
    """
    con = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    try:
        seasons = con.execute(
            "SELECT COUNT(DISTINCT season) FROM raw_match_results WHERE psch IS NOT NULL"
        ).fetchone()[0]
        assert seasons >= 13, (
            f"expected >=13 seasons with PSCH non-null (Pinnacle closing 2012-13+), got {seasons}"
        )
    finally:
        con.close()


def test_known_row_typed_value() -> None:
    """Spot-check a 2024-25 EPL match has typed closing odds populated."""
    con = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    try:
        row = con.execute(
            """
            SELECT b365ch, psch, ahc_line
            FROM raw_match_results
            WHERE league = 'EPL' AND season = '2024-2025'
              AND home_team = 'Man United' AND away_team = 'Fulham'
            """
        ).fetchone()
        assert row is not None, "expected Man United vs Fulham 2024-08-16 fixture row"
        b365ch, psch, ahc_line = row
        # Typed values should be populated and within reasonable odds ranges.
        assert b365ch is not None and 1.01 <= b365ch <= 100.0
        assert psch is not None and 1.01 <= psch <= 100.0
        # AH line is a handicap, can be negative.
        assert ahc_line is not None and -5.0 <= ahc_line <= 5.0
    finally:
        con.close()
