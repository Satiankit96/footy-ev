"""Unit tests for orchestration.state — pydantic types + state schema."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from footy_ev.orchestration.state import (
    BetDecision,
    CircuitBreakerEvent,
    MarketType,
    ModelProbability,
    OddsSnapshot,
)


def test_market_type_values():
    assert MarketType.OU_25.value == "ou_2.5"
    assert MarketType.MATCH_1X2.value == "1x2"


def test_odds_snapshot_round_trip():
    snap = OddsSnapshot(
        venue="kalshi",
        fixture_id="ARS-LIV",
        market=MarketType.OU_25,
        selection="over",
        odds_decimal=2.05,
        captured_at=datetime(2026, 5, 6, 22, tzinfo=UTC),
    )
    assert snap.staleness_seconds == 0
    assert snap.liquidity_gbp is None
    assert snap.model_dump()["market"] == "ou_2.5"


def test_model_probability_requires_features_hash():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ModelProbability(
            fixture_id="x",
            market=MarketType.OU_25,
            selection="over",
            p_raw=0.5,
            p_calibrated=0.5,
            model_version="x",
            uncertainty_se=0.01,
        )


def test_bet_decision_decimal_stake():
    bet = BetDecision(
        fixture_id="ARS-LIV",
        market=MarketType.OU_25,
        selection="over",
        odds_at_decision=2.05,
        p_calibrated=0.55,
        edge_pct=0.05,
        kelly_fraction_used=0.005,
        stake_gbp=Decimal("12.34"),
        bankroll_used=Decimal("1000.00"),
        venue="kalshi",
        decided_at=datetime.now(tz=UTC),
        features_hash="abc123",
    )
    assert isinstance(bet.stake_gbp, Decimal)
    assert bet.stake_gbp == Decimal("12.34")


def test_circuit_breaker_event():
    e = CircuitBreakerEvent(
        event_id="evt1",
        tripped_at=datetime.now(tz=UTC),
        reason="stale_odds",
        affected_source="kalshi",
        max_staleness_sec=520,
    )
    assert e.max_staleness_sec == 520
