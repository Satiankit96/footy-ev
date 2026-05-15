"""CLV adapter — rolling CLV, breakdown, sources, backfill.

Rolling CLV logic is the single source of truth; bets/clv/rolling delegates
here rather than duplicating the query.
"""

from __future__ import annotations

from typing import Any

import duckdb
from footy_ev.db import apply_migrations, apply_views
from footy_ev.runtime.clv_backfill import backfill_clv

from footy_ev_api.jobs.manager import Job


def _connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(read_only=read_only)
    apply_migrations(con)
    apply_views(con)
    return con


def get_clv_rolling(
    *,
    window: int = 100,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Return rolling N-bet CLV time series.

    Each element has: bet_index (1-based), decided_at, clv_pct (raw),
    rolling_clv (window-average), cumulative_clv (running mean so far).

    Bets without clv_pct are excluded (CLV not yet backfilled).
    """
    con = _connect()
    try:
        date_filter = "AND decided_at >= ?" if since else ""
        params: list[Any] = [since] if since else []

        rows = con.execute(
            f"""
            WITH ordered AS (
                SELECT
                    ROW_NUMBER() OVER (ORDER BY decided_at)  AS bet_index,
                    decided_at,
                    clv_pct
                FROM paper_bets
                WHERE clv_pct IS NOT NULL
                  {date_filter}
                ORDER BY decided_at
            )
            SELECT
                bet_index,
                CAST(decided_at AS VARCHAR)                              AS decided_at,
                clv_pct,
                AVG(clv_pct) OVER (
                    ORDER BY bet_index
                    ROWS BETWEEN ? PRECEDING AND CURRENT ROW
                )                                                        AS rolling_clv,
                AVG(clv_pct) OVER (
                    ORDER BY bet_index
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )                                                        AS cumulative_clv
            FROM ordered
            ORDER BY bet_index
            """,
            params + [window - 1],
        ).fetchall()

        cols = ["bet_index", "decided_at", "clv_pct", "rolling_clv", "cumulative_clv"]
        return [dict(zip(cols, r, strict=False)) for r in rows]
    finally:
        con.close()


def get_clv_breakdown(fixture_id: str | None = None) -> list[dict[str, Any]]:
    """Per-fixture CLV decomposition.

    Returns one row per fixture that has at least one settled bet with CLV data.
    """
    con = _connect()
    try:
        where = "AND fixture_id = ?" if fixture_id else ""
        params: list[Any] = [fixture_id] if fixture_id else []

        rows = con.execute(
            f"""
            SELECT
                fixture_id,
                market,
                selection,
                AVG(clv_pct)                              AS mean_clv,
                COUNT(*)                                  AS n_bets,
                SUM(CAST(stake_gbp AS DOUBLE))            AS total_staked,
                SUM(CAST(pnl_gbp AS DOUBLE))              AS total_pnl
            FROM paper_bets
            WHERE clv_pct IS NOT NULL
              AND settlement_status IN ('won', 'lost')
              {where}
            GROUP BY fixture_id, market, selection
            ORDER BY fixture_id, market, selection
            """,
            params,
        ).fetchall()

        cols = [
            "fixture_id",
            "market",
            "selection",
            "mean_clv",
            "n_bets",
            "total_staked",
            "total_pnl",
        ]
        result = []
        for r in rows:
            d = dict(zip(cols, r, strict=False))
            d["total_staked"] = str(round(float(d["total_staked"] or 0), 2))
            d["total_pnl"] = str(round(float(d["total_pnl"] or 0), 2))
            d["mean_clv"] = float(d["mean_clv"]) if d["mean_clv"] is not None else None
            result.append(d)
        return result
    finally:
        con.close()


def get_clv_sources() -> list[dict[str, Any]]:
    """Count bets by closing-odds benchmark source.

    Source is inferred from available data:
    - 'kalshi'  — closing_odds present and venue = 'kalshi' live snapshot
    - 'pinnacle' — closing_odds present (not matched to kalshi snapshot)
    - 'missing' — closing_odds IS NULL
    We use a simple proxy: if closing_odds is NOT NULL → kalshi (primary),
    else → missing. Pinnacle fallback is tracked similarly.
    The source label is stored as venue for simplicity.
    """
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT
                CASE
                    WHEN closing_odds IS NOT NULL THEN venue
                    ELSE 'missing'
                END AS source,
                COUNT(*) AS n_bets,
                AVG(clv_pct) AS mean_clv
            FROM paper_bets
            WHERE settlement_status IN ('won', 'lost')
            GROUP BY source
            ORDER BY n_bets DESC
            """,
        ).fetchall()

        cols = ["source", "n_bets", "mean_clv"]
        return [
            {
                **dict(zip(cols, r, strict=False)),
                "mean_clv": float(r[2]) if r[2] is not None else None,
            }
            for r in rows
        ]
    finally:
        con.close()


def run_clv_backfill(
    job: Job,
    broadcast: Any,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> None:
    """Run CLV backfill in-process using footy_ev.runtime.clv_backfill.

    Opens a read-write connection (backfill writes clv_pct / closing_odds).
    from_date / to_date are logged but not yet used to filter (backfill_clv
    processes all settled bets with NULL closing_odds).
    """
    import logging

    log = logging.getLogger(__name__)
    log.info("clv_backfill: from=%s to=%s", from_date, to_date)

    con = _connect(read_only=False)
    try:
        result = backfill_clv(con, venue="kalshi", dry_run=False)
    finally:
        con.close()

    log.info("clv_backfill result: %s", result)
