"""Single-pass paper-trader test against a mocked Betfair client.

Drives runtime.paper_trader.run_once end-to-end with an in-memory
warehouse and a fake BetfairClient that returns one OU 2.5 market with
favourable odds. Asserts that:
  - the LangGraph runs to completion
  - paper_bets receives the approved decision
  - langgraph_checkpoint_summaries records the invocation
  - circuit_breaker_log stays empty when no staleness trip
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.runtime import PaperTraderConfig, run_once
from footy_ev.venues.betfair import BetfairResponse

_FIXTURE_DATE = "2099-06-01"
_FIXTURE_ID = f"EPL|2098-2099|arsenal|liverpool|{_FIXTURE_DATE}"


@pytest.fixture
def warehouse(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    db_path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    apply_views(con)
    # Seed betfair→warehouse resolution so scraper can resolve "Arsenal v Liverpool"
    now = datetime(2024, 1, 1)
    for bf_name, team_id in [("Arsenal", "arsenal"), ("Liverpool", "liverpool")]:
        con.execute(
            "INSERT INTO betfair_team_aliases (betfair_team_name, team_id, confidence, resolved_at)"
            " VALUES (?, ?, 1.0, ?)",
            [bf_name, team_id, now],
        )
    for team_id in ("arsenal", "liverpool"):
        con.execute(
            "INSERT OR IGNORE INTO team_aliases (source, raw_name, team_id, confidence, resolved_at)"
            " VALUES ('football_data', ?, ?, 'manual', ?)",
            [team_id, team_id, now],
        )
    con.execute(
        "INSERT OR IGNORE INTO raw_match_results"
        " (league, season, div, match_date, home_team, away_team,"
        "  source_code, source_url, ingested_at, source_row_hash)"
        " VALUES ('EPL', '2098-2099', 'E0', ?, 'arsenal', 'liverpool',"
        "         'football_data', 'http://x', ?, 'hash-ars-liv-pt')",
        [_FIXTURE_DATE, now],
    )
    return con


def _events_payload() -> list[dict[str, Any]]:
    return [
        {
            "event": {
                "id": "33001",
                "name": "Arsenal v Liverpool",
                "openDate": f"{_FIXTURE_DATE}T14:00:00.000Z",
                "countryCode": "GB",
            }
        }
    ]


def _catalogue_payload() -> list[dict[str, Any]]:
    return [
        {
            "marketId": "1.33001.OU25",
            "marketName": "Over/Under 2.5 Goals",
            "event": {"id": "33001"},
        }
    ]


def _book_payload(over: float = 2.05) -> list[dict[str, Any]]:
    return [
        {
            "marketId": "1.33001.OU25",
            "lastMatchTime": datetime.now(tz=UTC).isoformat(),
            "runners": [
                {"selectionId": 1, "ex": {"availableToBack": [{"price": over, "size": 200.0}]}},
                {"selectionId": 2, "ex": {"availableToBack": [{"price": 1.85, "size": 200.0}]}},
            ],
        }
    ]


def _make_betfair_mock() -> MagicMock:
    bf = MagicMock()
    now = datetime.now(tz=UTC)
    bf.list_events.return_value = BetfairResponse(payload=_events_payload(), received_at=now)
    bf.list_market_catalogue.return_value = BetfairResponse(
        payload=_catalogue_payload(), received_at=now
    )
    bf.list_market_book.return_value = BetfairResponse(
        payload=_book_payload(), received_at=now, source_timestamp=now, staleness_seconds=10
    )
    return bf


def _score_fn(fixtures: list[str], as_of: Any) -> list[dict[str, Any]]:
    return [
        {
            "fixture_id": fid,
            "market": "ou_2.5",
            "selection": "over",
            "p_calibrated": 0.55,
            "p_raw": 0.55,
            "sigma_p": 0.0,
            "model_version": "xgb_ou25_v1",
        }
        for fid in fixtures
    ]


def test_run_once_writes_paper_bet_and_summary(
    warehouse: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    cfg = PaperTraderConfig(
        fixtures_ahead_days=7,
        bankroll_gbp=1000.0,
        edge_threshold_pct=0.03,
        db_path=tmp_path / "wh.duckdb",
        checkpoint_path=tmp_path / "checkpoints.sqlite",
    )
    out = run_once(
        cfg,
        betfair=_make_betfair_mock(),
        score_fn=_score_fn,
        warehouse_con=warehouse,
    )
    assert out["n_fixtures"] == 1
    assert out["n_candidates"] == 1
    assert out["n_approved"] == 1
    assert out["breaker_tripped"] is False

    n_bets = warehouse.execute("SELECT COUNT(*) FROM paper_bets").fetchone()[0]
    assert n_bets == 1

    n_summaries = warehouse.execute(
        "SELECT COUNT(*) FROM langgraph_checkpoint_summaries"
    ).fetchone()[0]
    assert n_summaries == 1

    n_breaker = warehouse.execute("SELECT COUNT(*) FROM circuit_breaker_log").fetchone()[0]
    assert n_breaker == 0


def test_run_once_logs_breaker_on_stale_data(
    warehouse: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    cfg = PaperTraderConfig(
        fixtures_ahead_days=7,
        bankroll_gbp=1000.0,
        edge_threshold_pct=0.03,
        db_path=tmp_path / "wh.duckdb",
        checkpoint_path=tmp_path / "checkpoints.sqlite",
    )
    bf = _make_betfair_mock()
    bf.list_market_book.return_value = BetfairResponse(
        payload=_book_payload(),
        received_at=datetime.now(tz=UTC),
        source_timestamp=datetime.now(tz=UTC),
        staleness_seconds=600,
    )
    out = run_once(cfg, betfair=bf, score_fn=_score_fn, warehouse_con=warehouse)
    assert out["breaker_tripped"] is True
    n_breaker = warehouse.execute("SELECT COUNT(*) FROM circuit_breaker_log").fetchone()[0]
    assert n_breaker >= 1
