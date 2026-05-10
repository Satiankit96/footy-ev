"""Unit tests for footy_ev.venues.resolution.

Tests:
  1. resolve_event: exact alias match → confidence=1.0, status=resolved.
  2. resolve_event: name variant alias → confidence < 1.0, status=resolved.
  3. resolve_event: missing alias → status=unresolved, fixture_id=None.
  4. resolve_event: two fixtures same teams same day → status=ambiguous.
  5. resolve_event: no kickoff_utc → fallback to team-only, confidence capped.
  6. resolve_market: OVER_UNDER_25 → ou_2.5 (seeded in migration 010).
  7. resolve_market: unknown code → None.
  8. resolve_selection: Over 2.5 Goals → over (seeded in migration 010).
  9. resolve_selection: unknown runner → None.
 10. parse_betfair_event_name: standard "Arsenal v Liverpool" split.
 11. parse_betfair_event_name: no " v " → returns (name, "").
 12. cache_resolution: upserts betfair_event_resolutions row.
 13. resolve_event_from_meta: happy path with name + openDate.
 14. resolve_event_from_meta: empty name → unresolved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.venues.resolution import (
    EventResolution,
    cache_resolution,
    parse_betfair_event_name,
    resolve_event,
    resolve_event_from_meta,
    resolve_market,
    resolve_selection,
)


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_migrations(c)
    apply_views(c)
    return c


def _seed_team_alias(
    con: duckdb.DuckDBPyConnection,
    betfair_name: str,
    team_id: str,
    confidence: float = 1.0,
) -> None:
    con.execute(
        """
        INSERT INTO betfair_team_aliases (betfair_team_name, team_id, confidence, resolved_at)
        VALUES (?, ?, ?, ?)
        """,
        [betfair_name, team_id, confidence, datetime(2024, 1, 1)],
    )


def _seed_fixture(
    con: duckdb.DuckDBPyConnection,
    fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    match_date: str = "2024-05-15",
) -> None:
    """Insert a minimal raw_match_results row so v_fixtures_epl can find it."""
    # Insert canonical team aliases (football_data source) for the teams
    for team_id in (home_team_id, away_team_id):
        con.execute(
            """
            INSERT OR IGNORE INTO team_aliases
                (source, raw_name, team_id, confidence, resolved_at)
            VALUES ('football_data', ?, ?, 'manual', ?)
            """,
            [team_id, team_id, datetime(2024, 1, 1)],
        )
    con.execute(
        """
        INSERT OR IGNORE INTO raw_match_results
            (league, season, div, match_date, home_team, away_team,
             source_code, source_url, ingested_at, source_row_hash)
        VALUES ('EPL', '2023-2024', 'E0', ?, ?, ?, 'football_data', 'http://x', ?, ?)
        """,
        [match_date, home_team_id, away_team_id, datetime(2024, 1, 1), f"hash-{fixture_id}"],
    )


# ---------------------------------------------------------------------------
# resolve_event
# ---------------------------------------------------------------------------


def test_resolve_event_exact_match(con: duckdb.DuckDBPyConnection) -> None:
    _seed_team_alias(con, "Arsenal", "arsenal", 1.0)
    _seed_team_alias(con, "Liverpool", "liverpool", 1.0)
    _seed_fixture(con, "fix1", "arsenal", "liverpool", "2024-05-15")

    result = resolve_event(
        con, "31415", "Arsenal", "Liverpool", datetime(2024, 5, 15, 14, 0, tzinfo=UTC)
    )
    assert result.status == "resolved"
    assert result.fixture_id is not None
    assert result.confidence == pytest.approx(1.0)


def test_resolve_event_alias_variant(con: duckdb.DuckDBPyConnection) -> None:
    _seed_team_alias(con, "Man City", "man_city", 0.92)
    _seed_team_alias(con, "Chelsea FC", "chelsea", 0.95)
    _seed_fixture(con, "fix2", "man_city", "chelsea", "2024-05-20")

    result = resolve_event(
        con, "99", "Man City", "Chelsea FC", datetime(2024, 5, 20, 14, 0, tzinfo=UTC)
    )
    assert result.status == "resolved"
    assert result.confidence == pytest.approx(0.92)


def test_resolve_event_missing_alias(con: duckdb.DuckDBPyConnection) -> None:
    result = resolve_event(
        con, "99", "Neverland FC", "Ghost United", datetime(2024, 5, 20, 14, 0, tzinfo=UTC)
    )
    assert result.status == "unresolved"
    assert result.fixture_id is None
    assert "Neverland FC" in result.reason


def test_resolve_event_ambiguous(con: duckdb.DuckDBPyConnection) -> None:
    _seed_team_alias(con, "Arsenal", "arsenal", 1.0)
    _seed_team_alias(con, "Liverpool", "liverpool", 1.0)
    # Two fixtures same teams same date (edge case, e.g. test data artifact)
    _seed_fixture(con, "fix_a", "arsenal", "liverpool", "2024-05-15")
    con.execute(
        """
        INSERT OR IGNORE INTO raw_match_results
            (league, season, div, match_date, home_team, away_team,
             source_code, source_url, ingested_at, source_row_hash)
        VALUES ('EPL', '2022-2023', 'E0', '2024-05-15', 'arsenal', 'liverpool',
                'football_data', 'http://y', ?, 'hash-dup')
        """,
        [datetime(2024, 1, 1)],
    )
    result = resolve_event(
        con, "31415", "Arsenal", "Liverpool", datetime(2024, 5, 15, 14, 0, tzinfo=UTC)
    )
    assert result.status == "ambiguous"
    assert result.fixture_id is None


def test_resolve_event_no_kickoff(con: duckdb.DuckDBPyConnection) -> None:
    _seed_team_alias(con, "Arsenal", "arsenal", 1.0)
    _seed_team_alias(con, "Liverpool", "liverpool", 1.0)
    _seed_fixture(con, "fix1", "arsenal", "liverpool", "2024-05-15")

    result = resolve_event(con, "31415", "Arsenal", "Liverpool", kickoff_utc=None)
    # Should resolve (most recent fixture) but confidence capped at 0.8
    assert result.status in ("resolved", "ambiguous")
    if result.status == "resolved":
        assert result.confidence <= 0.8


# ---------------------------------------------------------------------------
# resolve_market / resolve_selection (seeded by migration 010)
# ---------------------------------------------------------------------------


def test_resolve_market_ou25(con: duckdb.DuckDBPyConnection) -> None:
    assert resolve_market(con, "OVER_UNDER_25") == "ou_2.5"


def test_resolve_market_match_odds(con: duckdb.DuckDBPyConnection) -> None:
    assert resolve_market(con, "MATCH_ODDS") == "1x2"


def test_resolve_market_unknown(con: duckdb.DuckDBPyConnection) -> None:
    assert resolve_market(con, "UNKNOWN_MARKET") is None


def test_resolve_selection_over_25(con: duckdb.DuckDBPyConnection) -> None:
    assert resolve_selection(con, "ou_2.5", "Over 2.5 Goals") == "over"


def test_resolve_selection_under_25(con: duckdb.DuckDBPyConnection) -> None:
    assert resolve_selection(con, "ou_2.5", "Under 2.5 Goals") == "under"


def test_resolve_selection_unknown(con: duckdb.DuckDBPyConnection) -> None:
    assert resolve_selection(con, "ou_2.5", "Exactly 2.5 Goals") is None


# ---------------------------------------------------------------------------
# parse_betfair_event_name
# ---------------------------------------------------------------------------


def test_parse_event_name_standard() -> None:
    home, away = parse_betfair_event_name("Arsenal v Liverpool")
    assert home == "Arsenal"
    assert away == "Liverpool"


def test_parse_event_name_with_spaces() -> None:
    home, away = parse_betfair_event_name("Manchester City v Tottenham Hotspur")
    assert home == "Manchester City"
    assert away == "Tottenham Hotspur"


def test_parse_event_name_no_separator() -> None:
    home, away = parse_betfair_event_name("Arsenal vs Liverpool")
    assert home == "Arsenal vs Liverpool"
    assert away == ""


# ---------------------------------------------------------------------------
# cache_resolution
# ---------------------------------------------------------------------------


def test_cache_resolution_inserts_row(con: duckdb.DuckDBPyConnection) -> None:
    res = EventResolution(fixture_id="fix1", confidence=1.0, status="resolved", reason="ok")
    cache_resolution(con, "evt_123", res)
    row = con.execute(
        "SELECT betfair_event_id, fixture_id, status FROM betfair_event_resolutions"
        " WHERE betfair_event_id = 'evt_123'"
    ).fetchone()
    assert row is not None
    assert row[1] == "fix1"
    assert row[2] == "resolved"


def test_cache_resolution_upserts(con: duckdb.DuckDBPyConnection) -> None:
    res1 = EventResolution(fixture_id=None, confidence=0.0, status="unresolved", reason="x")
    cache_resolution(con, "evt_999", res1)
    res2 = EventResolution(fixture_id="fix2", confidence=0.95, status="resolved", reason="ok")
    cache_resolution(con, "evt_999", res2)
    row = con.execute(
        "SELECT status, fixture_id FROM betfair_event_resolutions WHERE betfair_event_id = 'evt_999'"
    ).fetchone()
    assert row[0] == "resolved"
    assert row[1] == "fix2"


# ---------------------------------------------------------------------------
# resolve_event_from_meta
# ---------------------------------------------------------------------------


def test_resolve_event_from_meta_happy(con: duckdb.DuckDBPyConnection) -> None:
    _seed_team_alias(con, "Arsenal", "arsenal", 1.0)
    _seed_team_alias(con, "Liverpool", "liverpool", 1.0)
    _seed_fixture(con, "fix1", "arsenal", "liverpool", "2024-05-15")

    meta = {"name": "Arsenal v Liverpool", "openDate": "2024-05-15T14:00:00.000Z"}
    result = resolve_event_from_meta(con, "31415", meta)
    assert result.status == "resolved"


def test_resolve_event_from_meta_empty_name(con: duckdb.DuckDBPyConnection) -> None:
    result = resolve_event_from_meta(con, "99", {"name": "", "openDate": ""})
    assert result.status == "unresolved"
    assert "empty event name" in result.reason
