"""Unit tests for orchestration.nodes.pricing."""

from __future__ import annotations

from datetime import UTC, datetime

from footy_ev.orchestration.nodes.pricing import decision_id, pricing_node
from footy_ev.orchestration.state import (
    BetDecision,
    MarketType,
    ModelProbability,
    OddsSnapshot,
)


def _prob(p_cal: float = 0.55) -> ModelProbability:
    return ModelProbability(
        fixture_id="ARS-LIV",
        market=MarketType.OU_25,
        selection="over",
        p_raw=p_cal,
        p_calibrated=p_cal,
        model_version="xgb_ou25_v1",
        features_hash="abc123def456",
        uncertainty_se=0.02,
    )


def _snap(odds: float = 2.05) -> OddsSnapshot:
    return OddsSnapshot(
        venue="kalshi",
        fixture_id="ARS-LIV",
        market=MarketType.OU_25,
        selection="over",
        odds_decimal=odds,
        captured_at=datetime.now(tz=UTC),
    )


def test_pricing_emits_candidate_above_threshold() -> None:
    out = pricing_node(
        {
            "model_probs": [_prob(0.55)],
            "odds_snapshots": [_snap(2.05)],
            "edge_threshold_pct": 0.03,
            "bankroll_gbp": 1000.0,
        }
    )
    assert len(out["candidate_bets"]) == 1
    bet = out["candidate_bets"][0]
    assert bet.edge_pct > 0.03


def test_pricing_filters_below_threshold() -> None:
    # 0.55 * 1.95 - 1 = 0.0725, above 3% threshold
    # 0.50 * 1.95 - 1 = -0.025, below
    out = pricing_node(
        {
            "model_probs": [_prob(0.50)],
            "odds_snapshots": [_snap(1.95)],
            "edge_threshold_pct": 0.03,
        }
    )
    assert out["candidate_bets"] == []


def test_pricing_short_circuits_on_breaker() -> None:
    out = pricing_node({"circuit_breaker_tripped": True})
    assert out == {"candidate_bets": []}


def test_pricing_picks_best_back_odds() -> None:
    s1 = _snap(2.00)
    s2 = _snap(2.10)
    out = pricing_node(
        {
            "model_probs": [_prob(0.55)],
            "odds_snapshots": [s1, s2],
        }
    )
    assert out["candidate_bets"][0].odds_at_decision == 2.10


def test_decision_id_is_deterministic() -> None:
    bet = BetDecision(
        fixture_id="ARS-LIV",
        market=MarketType.OU_25,
        selection="over",
        odds_at_decision=2.05,
        p_calibrated=0.55,
        edge_pct=0.05,
        kelly_fraction_used=0.005,
        stake_gbp=__import__("decimal").Decimal("5.00"),
        bankroll_used=__import__("decimal").Decimal("1000.00"),
        venue="kalshi",
        decided_at=datetime(2026, 5, 6, 22, 0, 0, tzinfo=UTC),
        features_hash="abc",
    )
    a = decision_id(bet)
    b = decision_id(bet)
    assert a == b
    assert len(a) == 24
