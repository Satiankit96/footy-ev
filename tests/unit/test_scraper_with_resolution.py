"""Unit tests for scraper_node with entity resolution wired.

Tests:
  1. Resolution disabled (no con): falls back to Betfair event ID as fixture_id.
  2. Resolution enabled: resolved events → warehouse fixture_id in snapshots.
  3. Resolution enabled: unresolved events → snapshots dropped.
  4. 3 events, 2 resolve, 1 doesn't: 2 snapshots + 2 resolved_fixture_ids.
  5. >50% unresolved → circuit breaker tripped with reason containing
     "unresolved_event".
  6. All events unresolved → 0 snapshots, breaker tripped.
  7. Existing scraper tests still pass (backward compat, no con).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.orchestration.nodes.scraper import scraper_node
from footy_ev.venues.betfair import BetfairResponse


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_migrations(c)
    apply_views(c)
    return c


def _seed_alias(con: duckdb.DuckDBPyConnection, betfair_name: str, team_id: str) -> None:
    con.execute(
        "INSERT INTO betfair_team_aliases (betfair_team_name, team_id, confidence, resolved_at)"
        " VALUES (?, ?, 1.0, ?)",
        [betfair_name, team_id, datetime(2024, 1, 1)],
    )


def _seed_fixture(con: duckdb.DuckDBPyConnection, home: str, away: str, date: str) -> str:
    for team_id in (home, away):
        con.execute(
            "INSERT OR IGNORE INTO team_aliases (source, raw_name, team_id, confidence, resolved_at)"
            " VALUES ('football_data', ?, ?, 'manual', ?)",
            [team_id, team_id, datetime(2024, 1, 1)],
        )
    con.execute(
        "INSERT OR IGNORE INTO raw_match_results"
        " (league, season, div, match_date, home_team, away_team,"
        "  source_code, source_url, ingested_at, source_row_hash)"
        " VALUES ('EPL', '2023-2024', 'E0', ?, ?, ?, 'football_data', 'http://x', ?, ?)",
        [date, home, away, datetime(2024, 1, 1), f"hash-{home}-{away}-{date}"],
    )
    return f"EPL|2023-2024|{home}|{away}|{date}"


def _book_resp(over: float = 2.05, staleness: int = 0) -> BetfairResponse:
    now = datetime.now(tz=UTC)
    return BetfairResponse(
        payload=[
            {
                "marketId": "1.1.OU25",
                "lastMatchTime": now.isoformat(),
                "runners": [
                    {"selectionId": 1, "ex": {"availableToBack": [{"price": over, "size": 100.0}]}},
                    {"selectionId": 2, "ex": {"availableToBack": [{"price": 1.85, "size": 100.0}]}},
                ],
            }
        ],
        received_at=now,
        source_timestamp=now - timedelta(seconds=staleness),
        staleness_seconds=staleness,
    )


def _meta(name: str, date: str = "2024-05-15") -> dict[str, Any]:
    return {"name": name, "openDate": f"{date}T14:00:00.000Z", "countryCode": "GB"}


# ---------------------------------------------------------------------------
# Backward compat: no con → existing behaviour
# ---------------------------------------------------------------------------


def test_scraper_no_con_uses_betfair_id() -> None:
    client = MagicMock()
    client.list_market_book.return_value = _book_resp()
    out = scraper_node(
        {"fixtures_to_process": ["evt_42"]},
        client=client,
        market_id_map={"evt_42": ["1.1.OU25"]},
        venue="betfair_exchange",
    )
    assert len(out["odds_snapshots"]) == 2
    assert out["odds_snapshots"][0].fixture_id == "evt_42"
    assert out["resolved_fixture_ids"] == []


# ---------------------------------------------------------------------------
# Resolution enabled
# ---------------------------------------------------------------------------


def test_scraper_resolved_event_uses_warehouse_id(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(con, "Arsenal", "arsenal")
    _seed_alias(con, "Liverpool", "liverpool")
    wh_fixture_id = _seed_fixture(con, "arsenal", "liverpool", "2024-05-15")

    client = MagicMock()
    client.list_market_book.return_value = _book_resp()
    out = scraper_node(
        {"fixtures_to_process": ["evt_1"]},
        client=client,
        market_id_map={"evt_1": ["1.1.OU25"]},
        event_meta_map={"evt_1": _meta("Arsenal v Liverpool")},
        con=con,
        venue="betfair_exchange",
    )
    assert len(out["odds_snapshots"]) == 2
    assert out["odds_snapshots"][0].fixture_id == wh_fixture_id
    assert wh_fixture_id in out["resolved_fixture_ids"]


def test_scraper_unresolved_event_drops_snapshots(con: duckdb.DuckDBPyConnection) -> None:
    """Unresolved event: no snapshots, no resolved_fixture_ids; no breaker (only 1 event)."""
    client = MagicMock()
    client.list_market_book.return_value = _book_resp()
    out = scraper_node(
        {"fixtures_to_process": ["evt_1"]},
        client=client,
        market_id_map={"evt_1": ["1.1.OU25"]},
        event_meta_map={"evt_1": _meta("Ghost City v Phantom United")},
        con=con,
        venue="betfair_exchange",
    )
    assert out["odds_snapshots"] == []
    assert out["resolved_fixture_ids"] == []
    # 1/1 = 100% unresolved → breaker tripped
    assert out["circuit_breaker_tripped"] is True
    assert "unresolved_event" in out["breaker_reason"]


def test_scraper_three_events_two_resolve(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(con, "Arsenal", "arsenal")
    _seed_alias(con, "Liverpool", "liverpool")
    _seed_alias(con, "Chelsea", "chelsea")
    _seed_alias(con, "Man City", "man_city")
    _seed_fixture(con, "arsenal", "liverpool", "2024-05-15")
    _seed_fixture(con, "chelsea", "man_city", "2024-05-16")

    client = MagicMock()
    client.list_market_book.return_value = _book_resp()
    out = scraper_node(
        {"fixtures_to_process": ["evt_1", "evt_2", "evt_3"]},
        client=client,
        market_id_map={
            "evt_1": ["mkt_1"],
            "evt_2": ["mkt_2"],
            "evt_3": ["mkt_3"],
        },
        event_meta_map={
            "evt_1": _meta("Arsenal v Liverpool"),
            "evt_2": _meta("Chelsea v Man City", "2024-05-16"),
            "evt_3": _meta("Ghost FC v Phantom United"),
        },
        con=con,
        venue="betfair_exchange",
    )
    # 2 resolved events × 2 runners = 4 snapshots
    assert len(out["odds_snapshots"]) == 4
    assert len(out["resolved_fixture_ids"]) == 2
    # 1/3 failure (33%) < 50% threshold → breaker NOT tripped
    assert out["circuit_breaker_tripped"] is False


def test_scraper_over_50pct_unresolved_trips_breaker(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(con, "Arsenal", "arsenal")
    _seed_alias(con, "Liverpool", "liverpool")
    _seed_fixture(con, "arsenal", "liverpool", "2024-05-15")

    client = MagicMock()
    client.list_market_book.return_value = _book_resp()
    out = scraper_node(
        {"fixtures_to_process": ["evt_1", "evt_2", "evt_3"]},
        client=client,
        market_id_map={"evt_1": ["m1"], "evt_2": ["m2"], "evt_3": ["m3"]},
        event_meta_map={
            "evt_1": _meta("Arsenal v Liverpool"),
            "evt_2": _meta("Ghost FC v Phantom United"),
            "evt_3": _meta("Neverland v Nowhere"),
        },
        con=con,
        venue="betfair_exchange",
    )
    # 2/3 = 67% fail → breaker tripped
    assert out["circuit_breaker_tripped"] is True
    assert "unresolved_event" in out["breaker_reason"]
