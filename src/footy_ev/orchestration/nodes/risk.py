"""Risk node — Kelly sizing + portfolio caps (BLUE_MAP s4)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from footy_ev.orchestration.state import BetDecision, BettingState
from footy_ev.risk import kelly_fraction_used, kelly_stake, portfolio_caps


def risk_node(state: BettingState) -> dict[str, Any]:
    if state.get("circuit_breaker_tripped"):
        return {"placed_bets": []}

    candidates = state.get("candidate_bets", [])
    bankroll = float(state.get("bankroll_gbp", 0.0))
    if bankroll <= 0 or not candidates:
        return {"placed_bets": []}

    sized: list[BetDecision] = []
    for c in candidates:
        sigma = c.sigma_p or 0.0
        f_used = kelly_fraction_used(c.p_calibrated, sigma, c.odds_at_decision)
        stake = kelly_stake(c.p_calibrated, sigma, c.odds_at_decision, bankroll)
        sized.append(
            c.model_copy(
                update={
                    "kelly_fraction_used": f_used,
                    "stake_gbp": stake,
                    "bankroll_used": Decimal(str(bankroll)),
                    "per_bet_cap_hit": _hit_per_bet_cap(f_used, c.odds_at_decision, c.p_calibrated),
                }
            )
        )

    sized = [s for s in sized if s.stake_gbp > 0]
    if not sized:
        return {"placed_bets": []}

    cap_input = [
        {
            "fixture_id": s.fixture_id,
            "market": s.market.value,
            "selection": s.selection,
            "stake_gbp": s.stake_gbp,
            "odds_quoted": s.odds_at_decision,
        }
        for s in sized
    ]
    capped = portfolio_caps(cap_input, bankroll=bankroll)
    capped_lookup: dict[tuple[str, str, str], dict[str, Any]] = {
        (r["fixture_id"], r["market"], r["selection"]): r for r in capped
    }

    approved: list[BetDecision] = []
    for s in sized:
        match = capped_lookup.get((s.fixture_id, s.market.value, s.selection))
        if match is None:
            continue
        approved.append(
            s.model_copy(
                update={
                    "stake_gbp": match["stake_gbp"],
                    "portfolio_cap_hit": bool(match.get("portfolio_cap_hit", False)),
                }
            )
        )

    return {"placed_bets": approved}


def _hit_per_bet_cap(f_used: float, odds: float, p_cal: float) -> bool:
    # If the Kelly module clamped the fraction at per_bet_cap_pct (default 0.02),
    # the optimal full-Kelly fraction was higher. We can't recompute the cap value
    # cleanly from outside, so this is a heuristic: if f_used is at the default
    # 2% cap to within 1e-6, mark it as hit.
    return abs(f_used - 0.02) < 1e-6
