"""Unit tests for risk.kelly — BLUE_MAP §4.1 formula correctness.

Tests:
  1. Hand-computed example matches formula output.
  2. Non-zero sigma_p shrinks stake vs zero sigma_p.
  3. CLV multiplier: negative recent_clv shrinks stake; positive expands.
  4. Per-bet cap enforced when Kelly fraction exceeds cap.
  5. Returns Decimal not float.
  6. Zero stake when edge negative after uncertainty haircut.
  7. Zero stake when odds <= 1.
"""

from __future__ import annotations

from decimal import Decimal

from footy_ev.risk.kelly import kelly_fraction_used, kelly_stake

# ---------------------------------------------------------------------------
# Hand-computed reference
# ---------------------------------------------------------------------------
# p_hat=0.55, sigma_p=0.0, odds=2.10, bankroll=1000
#   b = 2.10 - 1.0 = 1.10
#   p_lb = 0.55 (no uncertainty)
#   q = 0.45
#   f_full = (1.10 * 0.55 - 0.45) / 1.10 = (0.605 - 0.45) / 1.10 = 0.155 / 1.10 ≈ 0.14091
#   clv_multiplier = max(0.4, min(1.0, 0.5 + 10*0.0)) = 0.5
#   f_used = 0.25 * 0.5 * 0.14091 ≈ 0.01761
#   cap = 0.02 → no cap hit
#   stake = 0.01761 * 1000 = £17.61
_REF_P = 0.55
_REF_SIGMA = 0.0
_REF_ODDS = 2.10
_REF_BANKROLL = 1000.0
_REF_STAKE_APPROX = 17.61


def test_hand_computed_example():
    stake = kelly_stake(_REF_P, _REF_SIGMA, _REF_ODDS, _REF_BANKROLL)
    assert isinstance(stake, Decimal)
    assert abs(float(stake) - _REF_STAKE_APPROX) < 0.05, (
        f"expected ~£{_REF_STAKE_APPROX}, got £{stake}"
    )


def test_returns_decimal_not_float():
    stake = kelly_stake(0.55, 0.0, 2.0, 500.0)
    assert isinstance(stake, Decimal), "kelly_stake must return Decimal"


def test_uncertainty_shrinks_stake():
    """Non-zero sigma_p reduces stake vs zero sigma_p (same p_hat)."""
    stake_certain = kelly_stake(0.55, 0.0, 2.10, 1000.0)
    stake_uncertain = kelly_stake(0.55, 0.05, 2.10, 1000.0)
    assert stake_uncertain < stake_certain, "higher sigma_p should shrink stake via p_lb reduction"


def test_large_sigma_zeroes_stake():
    """sigma_p larger than edge forces p_lb below break-even → stake = 0."""
    # p_lb = 0.52 - 1.0 * 0.10 = 0.42 → negative Kelly at odds 2.0 → zero
    stake = kelly_stake(0.52, 0.10, 2.0, 1000.0)
    assert stake == Decimal("0.00")


def test_negative_clv_shrinks_via_multiplier():
    """Negative recent_clv_pct shrinks via CLV multiplier (floor 0.4)."""
    stake_neutral = kelly_stake(0.55, 0.0, 2.10, 1000.0, recent_clv_pct=0.0)
    stake_negative = kelly_stake(0.55, 0.0, 2.10, 1000.0, recent_clv_pct=-0.1)
    # Both hit clv_multiplier = 0.4 (floor) or neutral = 0.5; negative ≤ neutral
    assert stake_negative <= stake_neutral


def test_positive_clv_expands_via_multiplier():
    """recent_clv_pct=0.05 → multiplier=1.0 (ceiling), larger than neutral 0.5."""
    stake_neutral = kelly_stake(0.55, 0.0, 2.10, 1000.0, recent_clv_pct=0.0)
    stake_live = kelly_stake(0.55, 0.0, 2.10, 1000.0, recent_clv_pct=0.05)
    assert stake_live > stake_neutral


def test_per_bet_cap_enforced():
    """Very high edge bet is capped at per_bet_cap_pct * bankroll."""
    # p=0.70, odds=3.0: very high edge → full Kelly >> 2%
    stake = kelly_stake(0.70, 0.0, 3.0, 1000.0, per_bet_cap_pct=0.02)
    assert float(stake) <= 1000.0 * 0.02 + 0.01  # penny rounding tolerance


def test_zero_edge_after_haircut_returns_zero():
    """p_lb shrunk to exactly break-even → zero stake."""
    # break-even at odds 2.0 is p=0.5; p_lb = 0.5 - k*sigma = 0.5 → f_full=0
    stake = kelly_stake(0.5, 0.0, 2.0, 1000.0)
    assert stake == Decimal("0.00")


def test_odds_at_or_below_1_returns_zero():
    stake = kelly_stake(0.55, 0.0, 1.0, 1000.0)
    assert stake == Decimal("0.00")
    stake_below = kelly_stake(0.55, 0.0, 0.9, 1000.0)
    assert stake_below == Decimal("0.00")


def test_kelly_fraction_used_consistent_with_kelly_stake():
    """kelly_fraction_used * bankroll should equal kelly_stake (within rounding)."""
    bankroll = 2000.0
    frac = kelly_fraction_used(0.55, 0.02, 2.10)
    stake = kelly_stake(0.55, 0.02, 2.10, bankroll)
    expected = round(frac * bankroll, 2)
    assert abs(float(stake) - expected) <= 0.01
