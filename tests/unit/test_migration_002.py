"""Unit tests for migration 002 (promote closing-odds families to typed columns).

The migration is run inside a transaction with a Phase B audit gate. These tests
exercise that flow against an in-memory DuckDB so we can validate behavior
without touching the real warehouse.
"""

from __future__ import annotations

import duckdb
import pytest

from footy_ev.db import MIGRATIONS_DIR, apply_migrations
from footy_ev.ingestion.football_data.columns import REGISTRY, SOURCE_NAMES
from footy_ev.ingestion.football_data.parse import FootballDataRow

MIGRATION_002_PATH = MIGRATIONS_DIR / "002_promote_closing_odds.sql"

# ---------------------------------------------------------------------------- #
# Fixed expected count: pre-002 the registry had 64 entries; migration 002
# promotes 52 closing-odds + pre-match AH columns, so the post-002 registry is 116.
# ---------------------------------------------------------------------------- #
_REGISTRY_COUNT_PRE_002 = 64
_REGISTRY_COUNT_POST_002 = 116
_PROMOTED_SOURCE_NAMES: tuple[str, ...] = (
    # 1X2 closing (27)
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
    # O/U closing (10)
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
    # AH closing + pre-match agg (15)
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


def _fresh_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    return con


def _insert_sample_row(
    con: duckdb.DuckDBPyConnection,
    *,
    home_team: str,
    extras: dict[str, str] | None = None,
    b365ch: float | None = None,
) -> None:
    """Insert a minimal raw_match_results row for testing."""
    cols = [
        "league",
        "season",
        "source_code",
        "source_url",
        "ingested_at",
        "source_row_hash",
        "div",
        "match_date",
        "home_team",
        "away_team",
        "extras",
        "b365ch",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    con.execute(
        f"INSERT INTO raw_match_results ({', '.join(cols)}) VALUES ({placeholders})",  # noqa: S608
        [
            "EPL",
            "2024-2025",
            "E0",
            "http://test/",
            "2026-04-25 00:00:00",
            f"hash-{home_team}",
            "E0",
            "2024-08-16",
            home_team,
            "TestAway",
            extras,
            b365ch,
        ],
    )


def _apply_migration_002(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(MIGRATION_002_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------- #
# 1. Registry/parse smoke tests
# ---------------------------------------------------------------------------- #
def test_registry_grew_by_52() -> None:
    """Catches accidental misses or duplicates when extending the registry."""
    assert len(REGISTRY) == _REGISTRY_COUNT_POST_002, (
        f"expected {_REGISTRY_COUNT_POST_002} (= {_REGISTRY_COUNT_PRE_002}+52), "
        f"got {len(REGISTRY)}"
    )
    # Every promoted source name is now in the registry.
    for name in _PROMOTED_SOURCE_NAMES:
        assert name in SOURCE_NAMES, f"{name!r} missing from registry post-migration-002"


def test_pydantic_accepts_new_aliases() -> None:
    """Construct a FootballDataRow using all 52 new source aliases."""
    payload: dict[str, object] = {
        "Div": "E0",
        "Date": "16/08/2024",
        "HomeTeam": "Man United",
        "AwayTeam": "Fulham",
        "FTHG": 1,
        "FTAG": 0,
        "FTR": "H",
    }
    # Stuff every promoted alias with a distinct value so we can verify routing.
    for i, src in enumerate(_PROMOTED_SOURCE_NAMES):
        payload[src] = f"{1.10 + i * 0.01:.2f}"

    row = FootballDataRow.model_validate(payload)

    # Spot-check across categories.
    assert row.b365ch == pytest.approx(1.10)
    assert row.psch == pytest.approx(1.19)  # 10th in the closing-1X2 list (0-indexed 9)
    assert row.b365c_over_25 == pytest.approx(1.37)
    assert row.ahc_line == pytest.approx(1.47)
    assert row.max_ah_home == pytest.approx(1.58)

    # Nothing routed to extras (every alias is now declared).
    assert row.__pydantic_extra__ == {}


# ---------------------------------------------------------------------------- #
# 2. SQL behavior tests against an in-memory DuckDB
# ---------------------------------------------------------------------------- #
def test_migration_002_extracts_extras_to_typed() -> None:
    """Pre-002-shaped row gets typed cols populated and extras scrubbed."""
    con = _fresh_db()
    _insert_sample_row(
        con,
        home_team="Test1",
        extras={"B365CH": "1.75", "PSCH": "1.91", "AHCh": "-0.25", "X_KEEP": "untouched"},
        b365ch=None,
    )
    _apply_migration_002(con)

    row = con.execute(
        "SELECT b365ch, psch, ahc_line, extras FROM raw_match_results WHERE home_team = 'Test1'"
    ).fetchone()
    assert row is not None
    b365ch, psch, ahc_line, extras = row

    assert b365ch == pytest.approx(1.75)
    assert psch == pytest.approx(1.91)
    assert ahc_line == pytest.approx(-0.25)

    # Promoted keys gone from extras; unrelated keys preserved.
    assert "B365CH" not in extras
    assert "PSCH" not in extras
    assert "AHCh" not in extras
    assert extras.get("X_KEEP") == "untouched"


def test_migration_002_idempotent_against_prior_typed() -> None:
    """COALESCE direction: existing typed wins over stale extras on re-run."""
    con = _fresh_db()
    _insert_sample_row(
        con,
        home_team="Test2",
        extras={"B365CH": "9.99"},  # stale / wrong
        b365ch=1.75,  # loader-written truth
    )
    _apply_migration_002(con)

    row = con.execute(
        "SELECT b365ch, extras FROM raw_match_results WHERE home_team = 'Test2'"
    ).fetchone()
    assert row is not None
    b365ch, extras = row

    # Typed value preserved (NOT overwritten by stale extras 9.99).
    assert b365ch == pytest.approx(1.75)
    # Phase C still scrubbed the promoted key from extras.
    assert "B365CH" not in extras


def test_migration_002_handles_null_extras() -> None:
    """Rows with NULL extras are skipped by both UPDATE phases — no error."""
    con = _fresh_db()
    con.execute(
        """
        INSERT INTO raw_match_results
            (league, season, source_code, source_url, ingested_at, source_row_hash,
             div, match_date, home_team, away_team, extras)
        VALUES ('EPL', '2024-2025', 'E0', 'http://test/', '2026-04-25 00:00:00',
                'hash-null', 'E0', '2024-08-16', 'TestNull', 'TestAway', NULL)
        """
    )
    _apply_migration_002(con)  # must not raise

    extras = con.execute(
        "SELECT extras FROM raw_match_results WHERE home_team = 'TestNull'"
    ).fetchone()
    assert extras is not None
    assert extras[0] is None


def test_migration_002_audit_treats_empty_string_as_no_data() -> None:
    """Empty-string extras values are treated as 'no data', not as cast failures.

    The loader stores Python ``None`` (i.e., empty CSV cells) as ``""`` in the
    extras MAP. The audit gate must NOT fire on these — they represent rows
    where the bookmaker simply didn't quote that market for that match. Phase B
    leaves the typed column NULL (TRY_CAST('') -> NULL), and Phase C should
    still scrub the key from extras since the row carries no information.
    """
    con = _fresh_db()
    _insert_sample_row(
        con,
        home_team="TestEmpty",
        extras={"B365CH": "", "PSCH": "", "X_KEEP": "untouched"},
        b365ch=None,
    )

    _apply_migration_002(con)  # must not raise

    row = con.execute(
        "SELECT b365ch, psch, extras FROM raw_match_results WHERE home_team = 'TestEmpty'"
    ).fetchone()
    assert row is not None
    b365ch, psch, extras = row

    # Empty strings cast to NULL and are not data; typed columns stay NULL.
    assert b365ch is None
    assert psch is None
    # Phase C still scrubbed the promoted keys from extras.
    assert "B365CH" not in extras
    assert "PSCH" not in extras
    # Unrelated keys preserved.
    assert extras.get("X_KEEP") == "untouched"


def test_migration_002_audit_gate_rolls_back_phase_c_on_cast_failure() -> None:
    """If extraction can't keep pace with extras keys, audit halts before Phase C.

    Construct a state where typed_count < extras_count: a row whose extras has
    'B365CH' = 'not_a_number' (uncastable). After Phase B, b365ch stays NULL
    while extras still has the key. The audit's CAST trick raises, the
    transaction rolls back, and 'B365CH' is preserved in extras (so the operator
    can investigate without losing source data).
    """
    con = _fresh_db()
    _insert_sample_row(
        con,
        home_team="TestBad",
        extras={"B365CH": "not_a_number"},
        b365ch=None,
    )

    with pytest.raises(duckdb.ConversionException):
        _apply_migration_002(con)

    # The transaction was aborted by the audit assertion — DuckDB requires an
    # explicit ROLLBACK before further queries on the same connection.
    con.execute("ROLLBACK")

    # Phase C did NOT run: 'B365CH' is still in extras (rollback worked).
    row = con.execute(
        "SELECT b365ch, extras FROM raw_match_results WHERE home_team = 'TestBad'"
    ).fetchone()
    assert row is not None
    b365ch, extras = row
    assert b365ch is None
    assert "B365CH" in extras
