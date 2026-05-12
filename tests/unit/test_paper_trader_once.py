"""Single-pass paper-trader tests against a mocked KalshiClient.

Drives runtime.paper_trader.run_once end-to-end with an in-memory
warehouse. Tests:
  - stub client raises NotImplementedError → breaker tripped, summary written
  - mock client returns valid events → bet written, breaker clear
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
from footy_ev.venues.kalshi import KalshiResponse

_FIXTURE_DATE = "2099-06-01"
_FIXTURE_ID = f"EPL|2098-2099|arsenal|liverpool|{_FIXTURE_DATE}"
_EVENT_TICKER = "KXEPLTOTAL-99JUN01ARSLIVFAKE"


@pytest.fixture
def warehouse(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    db_path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    apply_views(con)
    # Seed Kalshi alias and warehouse fixture so resolution succeeds.
    now = datetime(2024, 1, 1)
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
    con.execute(
        "INSERT INTO kalshi_event_aliases (event_ticker, fixture_id, confidence, resolved_at)"
        " VALUES (?, ?, 1.0, ?)",
        [_EVENT_TICKER, _FIXTURE_ID, now],
    )
    return con


def _make_kalshi_mock_not_implemented() -> MagicMock:
    client = MagicMock()
    client.get_events.side_effect = NotImplementedError("parsers not yet wired")
    return client


def _make_kalshi_mock_with_events() -> MagicMock:
    """Returns a mock that provides one event with favourable odds."""
    client = MagicMock()
    now = datetime.now(tz=UTC)
    client.get_events.return_value = KalshiResponse(
        payload=[
            {
                "event_ticker": _EVENT_TICKER,
                "markets": [
                    {
                        "yes_bid_dollars": "0.6000",  # p=0.60 → decimal 1/0.60 ≈ 1.67
                        "no_bid_dollars": "0.4000",
                        "yes_bid_size_fp": "50.00",
                        "no_bid_size_fp": "50.00",
                    }
                ],
            }
        ],
        received_at=now,
        staleness_seconds=0,
    )
    return client


def _score_fn(fixtures: list[str], as_of: Any) -> list[dict[str, Any]]:
    return [
        {
            "fixture_id": fid,
            "market": "ou_2.5",
            "selection": "over",
            "p_calibrated": 0.65,
            "p_raw": 0.65,
            "sigma_p": 0.0,
            "model_version": "xgb_ou25_v1",
        }
        for fid in fixtures
    ]


def test_run_once_stub_client_trips_breaker(
    warehouse: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """NotImplementedError from get_events → breaker tripped, summary written."""
    cfg = PaperTraderConfig(
        db_path=tmp_path / "wh.duckdb",
        checkpoint_path=tmp_path / "checkpoints.sqlite",
    )
    out = run_once(
        cfg,
        client=_make_kalshi_mock_not_implemented(),
        score_fn=_score_fn,
        warehouse_con=warehouse,
    )
    assert out["breaker_tripped"] is True
    assert out["venue"] == "kalshi"

    n_summaries = warehouse.execute(
        "SELECT COUNT(*) FROM langgraph_checkpoint_summaries"
    ).fetchone()[0]
    assert n_summaries == 1

    n_breaker = warehouse.execute("SELECT COUNT(*) FROM circuit_breaker_log").fetchone()[0]
    assert n_breaker == 1


def test_run_once_with_events_writes_paper_bet(
    warehouse: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """Mock client returns one event with favourable odds → paper_bet written."""
    cfg = PaperTraderConfig(
        db_path=tmp_path / "wh.duckdb",
        checkpoint_path=tmp_path / "checkpoints.sqlite",
        edge_threshold_pct=0.03,
        bankroll_gbp=1000.0,
    )
    out = run_once(
        cfg,
        client=_make_kalshi_mock_with_events(),
        score_fn=_score_fn,
        warehouse_con=warehouse,
    )
    assert out["venue"] == "kalshi"
    assert out["breaker_tripped"] is False
    assert out["n_approved"] >= 1

    n_bets = warehouse.execute("SELECT COUNT(*) FROM paper_bets").fetchone()[0]
    assert n_bets >= 1

    n_summaries = warehouse.execute(
        "SELECT COUNT(*) FROM langgraph_checkpoint_summaries"
    ).fetchone()[0]
    assert n_summaries == 1
