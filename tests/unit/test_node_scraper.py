"""Unit tests for orchestration.nodes.scraper (Kalshi path)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.orchestration.nodes.scraper import scraper_node
from footy_ev.venues.kalshi import KalshiResponse


def _kalshi_resp(events: list[dict[str, Any]]) -> KalshiResponse:
    return KalshiResponse(
        payload=events,
        received_at=datetime.now(tz=UTC),
        staleness_seconds=0,
    )


def _event(ticker: str, yes_bid: float = 0.55, no_bid: float = 0.45) -> dict[str, Any]:
    return {
        "event_ticker": ticker,
        "markets": [
            {
                "yes_bid_dollars": str(yes_bid),
                "no_bid_dollars": str(no_bid),
                "yes_bid_size_fp": "10.00",
                "no_bid_size_fp": "10.00",
            }
        ],
    }


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_migrations(c)
    apply_views(c)
    return c


def _seed_alias(con: duckdb.DuckDBPyConnection, ticker: str, fixture_id: str) -> None:
    con.execute(
        "INSERT INTO kalshi_event_aliases (event_ticker, fixture_id, confidence, resolved_at)"
        " VALUES (?, ?, 1.0, ?)",
        [ticker, fixture_id, datetime(2026, 1, 1)],
    )


# ---------------------------------------------------------------------------
# NotImplementedError path (stub client, pre-5b)
# ---------------------------------------------------------------------------


def test_scraper_trips_breaker_on_not_implemented() -> None:
    client = MagicMock()
    client.get_events.side_effect = NotImplementedError("get_events stub")
    out = scraper_node({"fixtures_to_process": []}, client=client)
    assert out["circuit_breaker_tripped"] is True
    assert "not yet implemented" in out["breaker_reason"].lower()
    assert out["odds_snapshots"] == []


def test_scraper_trips_breaker_on_other_exception() -> None:
    client = MagicMock()
    client.get_events.side_effect = RuntimeError("network error")
    out = scraper_node({"fixtures_to_process": []}, client=client)
    assert out["circuit_breaker_tripped"] is True
    assert "RuntimeError" in out["breaker_reason"]


# ---------------------------------------------------------------------------
# Happy path — no con (uses event_ticker as fixture_id)
# ---------------------------------------------------------------------------


def test_scraper_no_con_uses_event_ticker_as_fixture_id() -> None:
    client = MagicMock()
    client.get_events.return_value = _kalshi_resp([_event("KXEPLTOTAL-26MAY24WHULEE")])
    out = scraper_node({"fixtures_to_process": []}, client=client)
    assert not out["circuit_breaker_tripped"]
    assert len(out["odds_snapshots"]) >= 1
    assert out["odds_snapshots"][0].fixture_id == "KXEPLTOTAL-26MAY24WHULEE"


def test_scraper_extracts_over_and_under_snapshots() -> None:
    client = MagicMock()
    client.get_events.return_value = _kalshi_resp([_event("EVT1", yes_bid=0.55, no_bid=0.45)])
    out = scraper_node({"fixtures_to_process": []}, client=client)
    selections = {s.selection for s in out["odds_snapshots"]}
    assert "over" in selections
    assert "under" in selections


def test_scraper_skips_event_with_zero_price() -> None:
    client = MagicMock()
    # yes_bid=0.0 is out of valid range → snapshot skipped
    client.get_events.return_value = _kalshi_resp([_event("EVT1", yes_bid=0.0, no_bid=0.0)])
    out = scraper_node({"fixtures_to_process": []}, client=client)
    assert out["odds_snapshots"] == []


# ---------------------------------------------------------------------------
# Resolution path
# ---------------------------------------------------------------------------


def test_scraper_with_con_resolves_to_fixture_id(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(con, "KXEPLTOTAL-26MAY24WHULEE", "EPL|2025-2026|whu|lee|2026-05-24")
    client = MagicMock()
    client.get_events.return_value = _kalshi_resp([_event("KXEPLTOTAL-26MAY24WHULEE")])
    out = scraper_node({"fixtures_to_process": []}, client=client, con=con)
    assert not out["circuit_breaker_tripped"]
    assert len(out["odds_snapshots"]) >= 1
    assert out["odds_snapshots"][0].fixture_id == "EPL|2025-2026|whu|lee|2026-05-24"


def test_scraper_unresolved_event_drops_snapshot(con: duckdb.DuckDBPyConnection) -> None:
    """Single unresolved event = 100% failure → breaker trips."""
    client = MagicMock()
    client.get_events.return_value = _kalshi_resp([_event("UNKNOWN-TICKER")])
    out = scraper_node({"fixtures_to_process": []}, client=client, con=con)
    assert out["odds_snapshots"] == []
    assert out["circuit_breaker_tripped"] is True
    assert "unresolved_event" in out["breaker_reason"]


def test_scraper_over_50pct_unresolved_trips_breaker(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(con, "EVT1", "fixture-1")
    client = MagicMock()
    client.get_events.return_value = _kalshi_resp(
        [
            _event("EVT1"),
            _event("EVT2"),
            _event("EVT3"),
        ]
    )
    out = scraper_node({"fixtures_to_process": []}, client=client, con=con)
    # 2/3 = 67% unresolved → breaker tripped
    assert out["circuit_breaker_tripped"] is True
    assert "unresolved_event" in out["breaker_reason"]


def test_scraper_under_50pct_unresolved_no_breaker(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(con, "EVT1", "fixture-1")
    _seed_alias(con, "EVT2", "fixture-2")
    client = MagicMock()
    client.get_events.return_value = _kalshi_resp(
        [
            _event("EVT1"),
            _event("EVT2"),
            _event("EVT3"),
        ]
    )
    out = scraper_node({"fixtures_to_process": []}, client=client, con=con)
    # 1/3 = 33% unresolved → no breaker
    assert out["circuit_breaker_tripped"] is False
    assert len(out["resolved_fixture_ids"]) == 2
