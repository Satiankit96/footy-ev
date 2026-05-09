"""Execution node — paper-only writer for Phase 3 step 1.

Hard constraint: real-money execution is gated on LIVE_TRADING=true AND
the bankroll discipline checks in PROJECT_INSTRUCTIONS s3. Even when
that gate flips, this node has NO Betfair placeBets call wired up — the
real-execution path lands in Phase 4. For now, every approved bet
becomes a row in paper_bets with `settlement_status='pending'`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import duckdb

from footy_ev.orchestration.nodes.pricing import decision_id
from footy_ev.orchestration.state import BetDecision, BettingState

_LOG = logging.getLogger(__name__)


def execution_node(
    state: BettingState,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Persist approved bets to paper_bets. No live placement."""
    approved: list[BetDecision] = state.get("placed_bets", [])
    if not approved:
        return {}

    live_flag = os.environ.get("LIVE_TRADING", "false").lower() == "true"
    if live_flag:
        # Reaching this branch in step 1 is a bug — there is no Betfair
        # placeBets call wired up. We log loudly and still write to
        # paper_bets so the audit trail is preserved.
        _LOG.warning(
            "LIVE_TRADING=true but no real-execution path is wired in step 1; "
            "treating %d approved bet(s) as paper.",
            len(approved),
        )

    if con is None:
        return {"placed_bets": approved}

    rows = []
    for bet in approved:
        rows.append(
            (
                decision_id(bet),
                bet.run_id,
                bet.fixture_id,
                bet.market.value,
                bet.selection,
                bet.p_calibrated,
                bet.sigma_p,
                bet.odds_at_decision,
                bet.venue,
                bet.edge_pct,
                bet.kelly_fraction_used,
                bet.stake_gbp,
                bet.bankroll_used,
                bet.features_hash,
                bet.decided_at,
            )
        )

    con.executemany(
        """
        INSERT INTO paper_bets (
            decision_id, run_id, fixture_id, market, selection,
            p_calibrated, sigma_p, odds_at_decision, venue, edge_pct,
            kelly_fraction_used, stake_gbp, bankroll_used, features_hash,
            decided_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (decision_id) DO NOTHING
        """,
        rows,
    )

    return {"placed_bets": approved}
