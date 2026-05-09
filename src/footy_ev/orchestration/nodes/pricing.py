"""Pricing node — Shin de-vig + edge threshold.

For each (fixture, market, selection) ModelProbability, find the best
matching odds in this tick's snapshots and compute:

    edge_pct = p_calibrated * odds_decimal - 1

Emit a candidate BetDecision when edge > threshold (default 3%, taken
from state).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from footy_ev.orchestration.state import (
    BetDecision,
    BettingState,
    OddsSnapshot,
)

DEFAULT_EDGE_THRESHOLD = 0.03


def pricing_node(state: BettingState) -> dict[str, Any]:
    if state.get("circuit_breaker_tripped"):
        return {"candidate_bets": []}

    probs = state.get("model_probs", [])
    snapshots = state.get("odds_snapshots", [])
    threshold = state.get("edge_threshold_pct", DEFAULT_EDGE_THRESHOLD)

    by_key: dict[tuple[str, str, str], OddsSnapshot] = {}
    for snap in snapshots:
        key = (snap.fixture_id, snap.market.value, snap.selection)
        # keep the best (highest) back odds for a given selection
        existing = by_key.get(key)
        if existing is None or snap.odds_decimal > existing.odds_decimal:
            by_key[key] = snap

    candidates: list[BetDecision] = []
    decided_at = datetime.now(tz=UTC)
    for prob in probs:
        key = (prob.fixture_id, prob.market.value, prob.selection)
        snap = by_key.get(key)
        if snap is None:
            continue
        edge = prob.p_calibrated * snap.odds_decimal - 1.0
        if edge < threshold:
            continue
        rationale = (
            f"p_cal={prob.p_calibrated:.3f} * odds={snap.odds_decimal:.2f} "
            f"= {prob.p_calibrated * snap.odds_decimal:.3f}; edge={edge:.3%}"
        )
        candidates.append(
            BetDecision(
                fixture_id=prob.fixture_id,
                market=prob.market,
                selection=prob.selection,
                odds_at_decision=snap.odds_decimal,
                p_calibrated=prob.p_calibrated,
                sigma_p=prob.uncertainty_se,
                edge_pct=edge,
                kelly_fraction_used=0.0,  # filled in by risk_node
                stake_gbp=Decimal("0.00"),
                bankroll_used=Decimal(str(state.get("bankroll_gbp", 0.0))),
                venue=snap.venue,
                decided_at=decided_at,
                features_hash=prob.features_hash,
                rationale=rationale,
                run_id=prob.run_id,
            )
        )

    return {"candidate_bets": candidates}


def decision_id(bet: BetDecision) -> str:
    """Deterministic id for paper_bets PK.

    Idempotent across runtime restarts: a re-run of the same fixture +
    market + selection at the exact same decided_at produces the same
    id, so the row is upserted not duplicated.
    """
    seed = (
        f"{bet.fixture_id}|{bet.market.value}|{bet.selection}|"
        f"{bet.decided_at.isoformat()}|{bet.venue}"
    )
    return hashlib.sha256(seed.encode()).hexdigest()[:24]
