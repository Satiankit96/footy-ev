"""Unit tests for orchestration.nodes.risk."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from footy_ev.orchestration.nodes.risk import risk_node
from footy_ev.orchestration.state import BetDecision, MarketType


def _candidate(p_cal: float = 0.55, odds: float = 2.05) -> BetDecision:
    return BetDecision(
        fixture_id="ARS-LIV",
        market=MarketType.OU_25,
        selection="over",
        odds_at_decision=odds,
        p_calibrated=p_cal,
        sigma_p=0.0,
        edge_pct=p_cal * odds - 1.0,
        kelly_fraction_used=0.0,
        stake_gbp=Decimal("0.00"),
        bankroll_used=Decimal("0.00"),
        venue="betfair_exchange",
        decided_at=datetime.now(tz=UTC),
        features_hash="abc",
    )


def test_risk_short_circuits_on_breaker() -> None:
    out = risk_node({"circuit_breaker_tripped": True})
    assert out == {"placed_bets": []}


def test_risk_returns_empty_with_zero_bankroll() -> None:
    out = risk_node({"candidate_bets": [_candidate()], "bankroll_gbp": 0.0})
    assert out == {"placed_bets": []}


def test_risk_sizes_via_kelly_and_caps() -> None:
    out = risk_node({"candidate_bets": [_candidate()], "bankroll_gbp": 1000.0})
    placed = out["placed_bets"]
    assert len(placed) == 1
    assert placed[0].stake_gbp > Decimal("0.00")
    assert placed[0].kelly_fraction_used > 0.0


def test_risk_drops_zero_kelly_candidates() -> None:
    # p < break-even at given odds → Kelly is zero
    out = risk_node({"candidate_bets": [_candidate(p_cal=0.30, odds=2.0)], "bankroll_gbp": 1000.0})
    assert out == {"placed_bets": []}
