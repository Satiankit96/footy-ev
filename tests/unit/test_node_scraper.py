"""Unit tests for orchestration.nodes.scraper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

from footy_ev.orchestration.nodes.scraper import scraper_node
from footy_ev.venues.betfair import BetfairResponse


def _book_payload(over: float = 2.05, under: float = 1.85) -> list[dict[str, Any]]:
    return [
        {
            "marketId": "1.1.OU25",
            "lastMatchTime": datetime.now(tz=UTC).isoformat(),
            "runners": [
                {"selectionId": 1, "ex": {"availableToBack": [{"price": over, "size": 100.0}]}},
                {"selectionId": 2, "ex": {"availableToBack": [{"price": under, "size": 100.0}]}},
            ],
        }
    ]


def _make_response(payload: Any, *, staleness: int = 0) -> BetfairResponse:
    return BetfairResponse(
        payload=payload,
        received_at=datetime.now(tz=UTC),
        source_timestamp=datetime.now(tz=UTC) - timedelta(seconds=staleness),
        staleness_seconds=staleness,
    )


def test_scraper_returns_empty_when_no_fixtures() -> None:
    client = MagicMock()
    out = scraper_node({"fixtures_to_process": []}, client=client, market_id_map={})
    assert out["odds_snapshots"] == []
    assert out["circuit_breaker_tripped"] is False


def test_scraper_returns_empty_without_market_map() -> None:
    client = MagicMock()
    out = scraper_node({"fixtures_to_process": ["ARS-LIV"]}, client=client, market_id_map=None)
    assert out["odds_snapshots"] == []


def test_scraper_extracts_ou25_snapshots() -> None:
    client = MagicMock()
    client.list_market_book.return_value = _make_response(_book_payload())
    out = scraper_node(
        {"fixtures_to_process": ["ARS-LIV"]},
        client=client,
        market_id_map={"ARS-LIV": ["1.1.OU25"]},
    )
    assert len(out["odds_snapshots"]) == 2
    selections = {s.selection for s in out["odds_snapshots"]}
    assert selections == {"over", "under"}


def test_scraper_trips_breaker_on_stale_response() -> None:
    client = MagicMock()
    client.list_market_book.return_value = _make_response(_book_payload(), staleness=600)
    out = scraper_node(
        {"fixtures_to_process": ["ARS-LIV"]},
        client=client,
        market_id_map={"ARS-LIV": ["1.1.OU25"]},
    )
    assert out["circuit_breaker_tripped"] is True
    assert "stale" in out["breaker_reason"].lower()


def test_scraper_trips_breaker_on_exception() -> None:
    client = MagicMock()
    client.list_market_book.side_effect = RuntimeError("connection reset")
    out = scraper_node(
        {"fixtures_to_process": ["ARS-LIV"]},
        client=client,
        market_id_map={"ARS-LIV": ["1.1.OU25"]},
    )
    assert out["circuit_breaker_tripped"] is True
    assert "RuntimeError" in out["breaker_reason"]
