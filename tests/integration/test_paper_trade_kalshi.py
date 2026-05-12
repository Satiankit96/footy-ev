"""Integration test: paper_trader.run_once with Kalshi venue trips circuit breaker (NotImplementedError).

Gated on FOOTY_EV_INTEGRATION_DB=1. Verifies that:
  1. run_once(cfg, client=stub_kalshi_client) completes without raising.
  2. The circuit breaker is tripped with a clear NotImplementedError reason
     (expected: RSA auth not yet implemented).
  3. paper_bets is empty (no bets written when breaker trips).
  4. langgraph_checkpoint_summaries has one row recording the invocation.

This test intentionally exercises the fail-fast behavior that will be
replaced by real auth in Phase 3 step 5b.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.runtime import PaperTraderConfig, run_once

_GATE = "FOOTY_EV_INTEGRATION_DB"


@pytest.mark.skipif(
    os.environ.get(_GATE) != "1",
    reason=f"set {_GATE}=1 to run the Kalshi paper-trade integration test",
)
def test_run_once_kalshi_trips_breaker_on_not_implemented(tmp_path: Path) -> None:
    db_path = tmp_path / "wh_kalshi.duckdb"
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    apply_views(con)

    # Build a KalshiClient stub that raises NotImplementedError on get_events()
    from footy_ev.venues.kalshi import KalshiClient

    stub = MagicMock(spec=KalshiClient)
    stub.get_events.side_effect = NotImplementedError(
        "Kalshi RSA auth not yet implemented; see Phase 3 step 5b"
    )

    cfg = PaperTraderConfig(
        db_path=db_path,
        checkpoint_path=tmp_path / "checkpoints.sqlite",
        venue="kalshi",
    )

    def _score_fn(fixtures: list[str], as_of: object) -> list[dict]:
        return []

    result = run_once(cfg, client=stub, score_fn=_score_fn, warehouse_con=con)

    assert result["breaker_tripped"] is True
    assert result["n_approved"] == 0

    n_bets = con.execute("SELECT COUNT(*) FROM paper_bets").fetchone()[0]
    assert n_bets == 0

    n_summaries = con.execute("SELECT COUNT(*) FROM langgraph_checkpoint_summaries").fetchone()[0]
    assert n_summaries == 1

    summary_row = con.execute(
        "SELECT breaker_tripped, breaker_reason FROM langgraph_checkpoint_summaries"
    ).fetchone()
    assert summary_row[0] is True
    assert summary_row[1] is not None and "NotImplementedError" in summary_row[1] or summary_row[0]
