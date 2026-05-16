"""Live-trading gate adapter — read-only warehouse queries, no writes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

from footy_ev_api.settings import Settings

_BANKROLL_FLAG = "BANKROLL_DISCIPLINE_CONFIRMED"
_CLV_BET_THRESHOLD = 1_000
_CLV_DAY_THRESHOLD = 60


def get_live_trading_status() -> dict[str, Any]:
    """Return gate status. enabled is always False — UI never acknowledges live mode."""
    reasons: list[str] = []
    if not os.environ.get(_BANKROLL_FLAG):
        reasons.append(
            f"{_BANKROLL_FLAG} env var not set — operator has not confirmed disposable bankroll"
        )
    reasons.append(
        f"CLV condition requires {_CLV_BET_THRESHOLD}+ settled bets over {_CLV_DAY_THRESHOLD}+ days "
        "with positive mean CLV — run /check-conditions to evaluate"
    )
    return {"enabled": False, "gate_reasons": reasons}


def _connect_ro() -> duckdb.DuckDBPyConnection | None:
    """Open a read-only warehouse connection, or return None if unavailable."""
    db = Path(Settings().warehouse_path)
    if not db.exists():
        return None
    con = duckdb.connect(str(db), read_only=True)
    from footy_ev.db import apply_migrations, apply_views

    apply_migrations(con)
    apply_views(con)
    return con


def _check_clv_condition(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Query paper_bets for settled bets with CLV data."""
    try:
        row = con.execute(
            """
            WITH settled AS (
                SELECT decided_at, clv_pct
                FROM paper_bets
                WHERE settlement_status != 'pending'
                  AND clv_pct IS NOT NULL
            )
            SELECT
                COUNT(*)                                                 AS bet_count,
                COALESCE(AVG(clv_pct), 0.0)                             AS mean_clv_pct,
                CASE
                    WHEN COUNT(*) > 0
                    THEN CAST(DATEDIFF('day', MIN(decided_at), MAX(decided_at)) AS INTEGER)
                    ELSE 0
                END                                                      AS days_span
            FROM settled
            """,
        ).fetchone()
        bet_count = int(row[0]) if row and row[0] is not None else 0
        mean_clv_pct = float(row[1]) if row and row[1] is not None else 0.0
        days_span = int(row[2]) if row and row[2] is not None else 0
    except Exception:  # noqa: BLE001
        bet_count, mean_clv_pct, days_span = 0, 0.0, 0

    met = bet_count >= _CLV_BET_THRESHOLD and days_span >= _CLV_DAY_THRESHOLD and mean_clv_pct > 0
    return {
        "met": met,
        "bet_count": bet_count,
        "days_span": days_span,
        "mean_clv_pct": round(mean_clv_pct, 4),
    }


def check_conditions() -> dict[str, Any]:
    """Run §3 gate checks. Read-only — zero writes to warehouse."""
    # Condition 2: bankroll discipline env flag
    flag_set = bool(os.environ.get(_BANKROLL_FLAG))
    bankroll = {
        "met": flag_set,
        "flag_name": _BANKROLL_FLAG,
        "flag_set": flag_set,
    }

    # Condition 1: CLV over 1000+ settled bets, 60+ days, positive mean
    con = _connect_ro()
    if con is None:
        clv = {"met": False, "bet_count": 0, "days_span": 0, "mean_clv_pct": 0.0}
    else:
        try:
            clv = _check_clv_condition(con)
        finally:
            con.close()

    return {
        "clv_condition": clv,
        "bankroll_condition": bankroll,
        "all_met": clv["met"] and bankroll["met"],
    }
