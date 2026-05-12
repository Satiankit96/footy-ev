"""Pipeline-state reporting for `run.py status` and the no-arg `run.py` invocation.

Queries the warehouse only — no API calls. Used by both `status` (read-only) and
`cycle` (which prints the table after running a pipeline pass).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import duckdb

DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"


def _humanize_age(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _rolling_clv(con: duckdb.DuckDBPyConnection, n: int) -> float | None:
    row = con.execute(
        """
        WITH last_n AS (
            SELECT clv_pct
            FROM paper_bets
            WHERE clv_pct IS NOT NULL
            ORDER BY decided_at DESC
            LIMIT ?
        )
        SELECT AVG(clv_pct) FROM last_n
        """,
        [n],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _clv_label(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "positive" if value > 0 else ("negative" if value < 0 else "flat")
    return f"{value:+.4f} ({sign})"


def print_status_table(
    con: duckdb.DuckDBPyConnection,
    emit: Callable[[str], None] = print,
) -> None:
    """Render the pipeline-state table per the run.py spec.

    Args:
        con: warehouse connection (read-only fine).
        emit: line printer; defaults to builtin print. Tests pass a capture.
    """
    now_utc = datetime.now(tz=UTC)
    base_url = os.environ.get("KALSHI_API_BASE_URL", DEMO_BASE_URL)
    venue_env = "production" if "demo" not in base_url else "demo"

    last_scrape_row = con.execute(
        "SELECT started_at, breaker_tripped, breaker_reason "
        "FROM langgraph_checkpoint_summaries ORDER BY started_at DESC LIMIT 1"
    ).fetchone()

    def _scalar(sql: str, params: list[Any] | None = None) -> int:
        row = con.execute(sql, params or []).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    n_aliases = _scalar("SELECT COUNT(*) FROM kalshi_event_aliases")

    today = date.today()
    n_snaps = _scalar(
        "SELECT COUNT(*) FROM live_odds_snapshots WHERE CAST(received_at AS DATE) = ?",
        [today],
    )
    n_preds = _scalar(
        "SELECT COUNT(*) FROM model_predictions WHERE CAST(as_of AS DATE) = ?",
        [today],
    )
    today_row = con.execute(
        """
        SELECT COALESCE(SUM(n_candidate_bets),0), COALESCE(SUM(n_approved_bets),0)
        FROM langgraph_checkpoint_summaries
        WHERE CAST(started_at AS DATE) = ?
        """,
        [today],
    ).fetchone()
    today_candidates = int(today_row[0]) if today_row else 0
    today_approved = int(today_row[1]) if today_row else 0

    clv_100 = _rolling_clv(con, 100)
    clv_500 = _rolling_clv(con, 500)

    last_bets = con.execute(
        """
        SELECT fixture_id, market, selection, odds_at_decision, clv_pct, settlement_status
        FROM paper_bets
        ORDER BY decided_at DESC LIMIT 5
        """
    ).fetchall()

    emit("=== footy-ev pipeline state ===")
    emit(f"UTC time:           {now_utc.isoformat()}")
    emit(f"Active venue:       kalshi ({venue_env})")
    emit(f"Base URL:           {base_url}")
    emit("")

    if last_scrape_row is None:
        emit("Last scrape:        (none yet)")
        emit("Circuit breaker:    OK")
    else:
        started_at, breaker, reason = last_scrape_row
        ts = started_at if started_at.tzinfo else started_at.replace(tzinfo=UTC)
        emit(f"Last scrape:        {started_at} ({_humanize_age(now_utc - ts)} ago)")
        if breaker:
            emit(f"Circuit breaker:    TRIPPED ({reason or 'unknown'})")
        else:
            emit("Circuit breaker:    OK")
    emit("")

    emit(f"Aliases:            {n_aliases} events resolved")
    emit(f"Today's snapshots:  {n_snaps}")
    emit(f"Today's predictions: {n_preds}")
    emit(f"Today's paper bets:  {today_candidates} candidates, {today_approved} placed")
    emit("")

    emit(f"Rolling 100-bet CLV: {_clv_label(clv_100)}")
    emit(f"Rolling 500-bet CLV: {_clv_label(clv_500)}")
    if last_bets:
        emit("Last 5 paper bets:")
        for r in last_bets:
            fid, mkt, sel, odds, clv, status = r
            clv_str = f"{clv:+.4f}" if clv is not None else "n/a"
            emit(f"  {fid} {mkt} {sel} @ {odds:.2f} -> CLV {clv_str} ({status or 'pending'})")
    emit("")
    emit("Run `uv run python run.py dashboard` for full UI.")
    emit("=================================================")
