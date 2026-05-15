"""Risk adapter — exposure, bankroll, and Kelly preview.

kelly_preview is a pure function that delegates to footy_ev.risk.kelly.kelly_stake
for the canonical stake calculation, while exposing the intermediate values needed
for the preview display.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import duckdb
from footy_ev.db import apply_migrations, apply_views
from footy_ev.risk.kelly import kelly_stake


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(read_only=True)
    apply_migrations(con)
    apply_views(con)
    return con


def get_exposure() -> dict[str, Any]:
    """Return current open exposure: per-fixture, today, and total.

    All monetary values serialised as strings (Decimal discipline).
    Only 'pending' bets are counted; settled bets are excluded.
    """
    con = _connect()
    try:
        per_fixture_rows = con.execute(
            """
            SELECT
                fixture_id,
                CAST(SUM(CAST(stake_gbp AS DOUBLE)) AS DOUBLE) AS open_stake
            FROM paper_bets
            WHERE settlement_status = 'pending'
            GROUP BY fixture_id
            ORDER BY open_stake DESC
            """,
        ).fetchall()

        per_fixture: list[dict[str, str]] = [
            {
                "fixture_id": str(r[0]),
                "open_stake": str(round(float(r[1]), 2)),
            }
            for r in per_fixture_rows
        ]

        today_row = con.execute(
            """
            SELECT SUM(CAST(stake_gbp AS DOUBLE))
            FROM paper_bets
            WHERE settlement_status = 'pending'
              AND CAST(decided_at AS DATE) = CURRENT_DATE
            """,
        ).fetchone()
        today_open = float(today_row[0]) if today_row and today_row[0] is not None else 0.0

        total_row = con.execute(
            """
            SELECT SUM(CAST(stake_gbp AS DOUBLE))
            FROM paper_bets
            WHERE settlement_status = 'pending'
            """,
        ).fetchone()
        total_open = float(total_row[0]) if total_row and total_row[0] is not None else 0.0

        return {
            "today_open": str(round(today_open, 2)),
            "total_open": str(round(total_open, 2)),
            "per_fixture": per_fixture,
        }
    finally:
        con.close()


def get_bankroll() -> dict[str, Any]:
    """Return current bankroll, peak, drawdown, and sparkline history.

    Uses bankroll_used from paper_bets as a running balance proxy.
    Sparkline is the last 100 bets ordered chronologically.
    """
    con = _connect()
    try:
        sparkline_rows = con.execute(
            """
            WITH recent AS (
                SELECT
                    CAST(decided_at AS VARCHAR) AS decided_at,
                    CAST(bankroll_used AS DOUBLE) AS bankroll
                FROM paper_bets
                ORDER BY decided_at DESC
                LIMIT 100
            )
            SELECT decided_at, bankroll FROM recent ORDER BY decided_at
            """,
        ).fetchall()

        sparkline = [
            {"decided_at": str(r[0]), "bankroll": str(round(float(r[1]), 2))}
            for r in sparkline_rows
        ]

        if not sparkline:
            return {
                "current": "0.00",
                "peak": "0.00",
                "drawdown_pct": 0.0,
                "sparkline": [],
            }

        latest_row = con.execute(
            """
            SELECT CAST(bankroll_used AS DOUBLE)
            FROM paper_bets
            ORDER BY decided_at DESC
            LIMIT 1
            """,
        ).fetchone()

        peak_row = con.execute(
            """
            SELECT MAX(CAST(bankroll_used AS DOUBLE))
            FROM paper_bets
            """,
        ).fetchone()

        current = float(latest_row[0]) if latest_row and latest_row[0] is not None else 0.0
        peak = float(peak_row[0]) if peak_row and peak_row[0] is not None else 0.0
        drawdown_pct = (peak - current) / peak if peak > 0.0 else 0.0

        return {
            "current": str(round(current, 2)),
            "peak": str(round(peak, 2)),
            "drawdown_pct": drawdown_pct,
            "sparkline": sparkline,
        }
    finally:
        con.close()


def kelly_preview(
    p_hat: float,
    sigma_p: float,
    odds: float,
    base_fraction: float,
    uncertainty_k: float,
    per_bet_cap_pct: float,
    recent_clv_pct: float,
    bankroll: str,
) -> dict[str, Any]:
    """Compute Kelly stake and intermediates. Pure function — zero DB access.

    Delegates to footy_ev.risk.kelly.kelly_stake for the canonical stake value.
    Computes the same intermediate steps so the operator can inspect each stage
    of the calculation. Equivalence with kelly_stake() is proven in test_risk.py.

    Args:
        p_hat: calibrated win probability.
        sigma_p: model uncertainty (bootstrap std-dev).
        odds: decimal odds.
        base_fraction: fractional Kelly base (default 0.25).
        uncertainty_k: std-dev haircut multiplier (default 1.0).
        per_bet_cap_pct: hard per-bet cap as fraction of bankroll (default 0.02).
        recent_clv_pct: rolling CLV for clv_multiplier shrinkage.
        bankroll: current bankroll in GBP as a Decimal string.

    Returns:
        Dict with stake (str), f_full, f_used, p_lb, clv_multiplier, per_bet_cap_hit.
    """
    bankroll_f = float(Decimal(bankroll))

    # Step 1 — lower-bound win probability (same as kelly_stake)
    p_lb = max(0.0, p_hat - uncertainty_k * sigma_p)

    # Step 3 — CLV-aware multiplier (computed before early-returns so it's always present)
    clv_multiplier = max(0.4, min(1.0, 0.5 + 10.0 * recent_clv_pct))

    b = odds - 1.0
    if b <= 0.0 or p_lb <= 0.0:
        stake = kelly_stake(
            p_hat,
            sigma_p,
            odds,
            bankroll_f,
            base_fraction=base_fraction,
            uncertainty_k=uncertainty_k,
            per_bet_cap_pct=per_bet_cap_pct,
            recent_clv_pct=recent_clv_pct,
        )
        return {
            "stake": str(stake),
            "f_full": 0.0,
            "f_used": 0.0,
            "p_lb": p_lb,
            "clv_multiplier": clv_multiplier,
            "per_bet_cap_hit": False,
        }

    # Step 2 — full Kelly on lower-bounded probability
    q = 1.0 - p_lb
    f_full = max(0.0, (b * p_lb - q) / b)

    if f_full <= 0.0:
        stake = kelly_stake(
            p_hat,
            sigma_p,
            odds,
            bankroll_f,
            base_fraction=base_fraction,
            uncertainty_k=uncertainty_k,
            per_bet_cap_pct=per_bet_cap_pct,
            recent_clv_pct=recent_clv_pct,
        )
        return {
            "stake": str(stake),
            "f_full": f_full,
            "f_used": 0.0,
            "p_lb": p_lb,
            "clv_multiplier": clv_multiplier,
            "per_bet_cap_hit": False,
        }

    # Step 3 — fractional Kelly with CLV multiplier, then hard cap
    f_uncapped = base_fraction * clv_multiplier * f_full
    per_bet_cap_hit = f_uncapped > per_bet_cap_pct
    f_used = min(f_uncapped, per_bet_cap_pct)

    # Canonical stake from kelly_stake() — proves equivalence in tests
    stake = kelly_stake(
        p_hat,
        sigma_p,
        odds,
        bankroll_f,
        base_fraction=base_fraction,
        uncertainty_k=uncertainty_k,
        per_bet_cap_pct=per_bet_cap_pct,
        recent_clv_pct=recent_clv_pct,
    )

    return {
        "stake": str(stake),
        "f_full": f_full,
        "f_used": f_used,
        "p_lb": p_lb,
        "clv_multiplier": clv_multiplier,
        "per_bet_cap_hit": per_bet_cap_hit,
    }
