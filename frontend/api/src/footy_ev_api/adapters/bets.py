"""Paper bets adapter — read-only queries against paper_bets table.

Rolling CLV logic lives in clv.py (single source of truth).
Kelly breakdown intermediate values are derived here from stored fields.
"""

from __future__ import annotations

from typing import Any

import duckdb
from footy_ev.db import apply_migrations, apply_views

_BASE_FRACTION = 0.25
_UNCERTAINTY_K = 1.0
_PER_BET_CAP = 0.02


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(read_only=True)
    apply_migrations(con)
    apply_views(con)
    return con


def _derive_kelly(
    p_calibrated: float,
    sigma_p: float | None,
    odds: float,
    kelly_fraction_used: float,
    bankroll_used: float,
) -> dict[str, Any]:
    """Derive Kelly intermediate values for the audit display.

    Uses the same formula as src/footy_ev/risk/kelly.py so the operator
    can reproduce each step from the displayed inputs.
    """
    sig = sigma_p if sigma_p is not None else 0.0
    p_lb = max(0.0, p_calibrated - _UNCERTAINTY_K * sig)
    b = odds - 1.0
    q = 1.0 - p_lb

    if b > 0.0 and p_lb > 0.0:
        f_full = (b * p_lb - q) / b
        f_full = max(0.0, f_full)
    else:
        f_full = 0.0

    per_bet_cap_hit = abs(kelly_fraction_used - _PER_BET_CAP) < 1e-9

    return {
        "p_hat": p_calibrated,
        "sigma_p": sig,
        "uncertainty_k": _UNCERTAINTY_K,
        "p_lb": p_lb,
        "b": b,
        "q": q,
        "f_full": f_full,
        "base_fraction": _BASE_FRACTION,
        "per_bet_cap_pct": _PER_BET_CAP,
        "f_used": kelly_fraction_used,
        "per_bet_cap_hit": per_bet_cap_hit,
        "bankroll_used": str(bankroll_used),
    }


def list_bets(
    *,
    status: str | None = None,
    fixture_id: str | None = None,
    venue: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return paginated paper_bets rows with optional filters."""
    con = _connect()
    try:
        conditions: list[str] = []
        params: list[Any] = []

        if status:
            conditions.append("settlement_status = ?")
            params.append(status)
        if fixture_id:
            conditions.append("fixture_id ILIKE ?")
            params.append(f"%{fixture_id}%")
        if venue:
            conditions.append("venue = ?")
            params.append(venue)
        if date_from:
            conditions.append("decided_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("decided_at <= ?")
            params.append(date_to)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        total_row = con.execute(
            f"SELECT COUNT(*) FROM paper_bets {where}",
            params,
        ).fetchone()
        total = int(total_row[0]) if total_row else 0

        rows = con.execute(
            f"""
            SELECT decision_id, fixture_id, market, selection,
                   odds_at_decision, CAST(stake_gbp AS VARCHAR) AS stake_gbp,
                   edge_pct, kelly_fraction_used, settlement_status,
                   clv_pct, decided_at, venue
            FROM paper_bets
            {where}
            ORDER BY decided_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        cols = [
            "decision_id",
            "fixture_id",
            "market",
            "selection",
            "odds_at_decision",
            "stake_gbp",
            "edge_pct",
            "kelly_fraction_used",
            "settlement_status",
            "clv_pct",
            "decided_at",
            "venue",
        ]
        bets = [dict(zip(cols, row, strict=False)) for row in rows]
        for b in bets:
            if b["decided_at"] is not None:
                b["decided_at"] = str(b["decided_at"])
        return {"bets": bets, "total": total}
    finally:
        con.close()


def get_bet(decision_id: str) -> dict[str, Any] | None:
    """Return full bet detail with derived Kelly breakdown."""
    con = _connect()
    try:
        row = con.execute(
            """
            SELECT decision_id, run_id, fixture_id, market, selection,
                   p_calibrated, sigma_p, odds_at_decision, venue, edge_pct,
                   kelly_fraction_used, CAST(stake_gbp AS VARCHAR) AS stake_gbp,
                   CAST(bankroll_used AS VARCHAR) AS bankroll_used,
                   features_hash, decided_at, settlement_status, settled_at,
                   CAST(pnl_gbp AS VARCHAR) AS pnl_gbp,
                   closing_odds, clv_pct
            FROM paper_bets
            WHERE decision_id = ?
            """,
            [decision_id],
        ).fetchone()

        if row is None:
            return None

        cols = [
            "decision_id",
            "run_id",
            "fixture_id",
            "market",
            "selection",
            "p_calibrated",
            "sigma_p",
            "odds_at_decision",
            "venue",
            "edge_pct",
            "kelly_fraction_used",
            "stake_gbp",
            "bankroll_used",
            "features_hash",
            "decided_at",
            "settlement_status",
            "settled_at",
            "pnl_gbp",
            "closing_odds",
            "clv_pct",
        ]
        bet = dict(zip(cols, row, strict=False))
        for ts in ("decided_at", "settled_at"):
            if bet[ts] is not None:
                bet[ts] = str(bet[ts])

        # Derive Kelly breakdown
        bet["kelly_breakdown"] = _derive_kelly(
            p_calibrated=float(bet["p_calibrated"]),
            sigma_p=float(bet["sigma_p"]) if bet["sigma_p"] is not None else None,
            odds=float(bet["odds_at_decision"]),
            kelly_fraction_used=float(bet["kelly_fraction_used"]),
            bankroll_used=float(bet["bankroll_used"] or 0),
        )

        # Edge math: edge = p_calibrated * odds - 1 (paper bets assume 0 commission)
        p = float(bet["p_calibrated"])
        o = float(bet["odds_at_decision"])
        bet["edge_math"] = {
            "p_calibrated": p,
            "odds_decimal": o,
            "commission": 0.0,
            "edge": p * o - 1.0 - 0.0,
            "edge_pct_stored": bet["edge_pct"],
        }

        return bet
    finally:
        con.close()


def get_bets_summary(period: str = "all") -> dict[str, Any]:
    """Aggregate stats: total bets, wins, ROI, mean CLV, max drawdown."""
    con = _connect()
    try:
        if period == "7d":
            date_filter = "AND decided_at >= NOW() - INTERVAL '7 days'"
        elif period == "30d":
            date_filter = "AND decided_at >= NOW() - INTERVAL '30 days'"
        else:
            date_filter = ""

        row = con.execute(
            f"""
            SELECT
                COUNT(*)                                                  AS total_bets,
                COUNT(*) FILTER (WHERE settlement_status = 'won')         AS wins,
                COUNT(*) FILTER (WHERE settlement_status = 'lost')        AS losses,
                COUNT(*) FILTER (WHERE settlement_status = 'pending')     AS pending,
                COALESCE(SUM(CAST(pnl_gbp AS DOUBLE)), 0)                AS total_pnl,
                COALESCE(SUM(CAST(stake_gbp AS DOUBLE)), 0)              AS total_staked,
                AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL)          AS mean_clv,
                MIN(clv_pct) FILTER (WHERE clv_pct IS NOT NULL)          AS min_clv,
                MAX(clv_pct) FILTER (WHERE clv_pct IS NOT NULL)          AS max_clv
            FROM paper_bets
            WHERE 1=1 {date_filter}
            """,
        ).fetchone()

        if row is None:
            return _empty_summary()

        (
            total,
            wins,
            losses,
            pending,
            total_pnl,
            total_staked,
            mean_clv,
            min_clv,
            max_clv,
        ) = row

        roi = float(total_pnl) / float(total_staked) if float(total_staked) > 0 else 0.0

        return {
            "period": period,
            "total_bets": int(total),
            "wins": int(wins),
            "losses": int(losses),
            "pending": int(pending),
            "total_pnl": str(round(float(total_pnl), 2)),
            "total_staked": str(round(float(total_staked), 2)),
            "roi": roi,
            "mean_clv": float(mean_clv) if mean_clv is not None else None,
            "min_clv": float(min_clv) if min_clv is not None else None,
            "max_clv": float(max_clv) if max_clv is not None else None,
        }
    finally:
        con.close()


def _empty_summary() -> dict[str, Any]:
    return {
        "period": "all",
        "total_bets": 0,
        "wins": 0,
        "losses": 0,
        "pending": 0,
        "total_pnl": "0.00",
        "total_staked": "0.00",
        "roi": 0.0,
        "mean_clv": None,
        "min_clv": None,
        "max_clv": None,
    }
