"""Unit tests for risk.portfolio — BLUE_MAP §4.2 cap enforcement.

Tests:
  1. Per-day cap: total stake sum respects 10% bankroll limit.
  2. Per-fixture cap: multiple markets on same fixture are capped together.
  3. Correlation collapsing: Over 2.5 + BTTS on same fixture share the fixture cap.
  4. Zero-stake candidates are excluded from output.
  5. Stakes downsized proportionally when cap binds.
  6. Output preserves non-stake fields from input.
"""

from __future__ import annotations

from decimal import Decimal

from footy_ev.risk.portfolio import portfolio_caps


def _bet(fixture_id: str, market: str, selection: str, stake: float) -> dict:
    return {
        "fixture_id": fixture_id,
        "market": market,
        "selection": selection,
        "stake_gbp": Decimal(str(stake)),
        "odds_quoted": 2.0,
    }


# ---------------------------------------------------------------------------
# Per-day cap
# ---------------------------------------------------------------------------


def test_per_day_cap_respected():
    """Sum of approved stakes <= per_day_cap_pct * bankroll."""
    bets = [_bet("f1", "ou_2.5", "over", 15.0) for _ in range(20)]
    result = portfolio_caps(bets, bankroll=1000.0, per_day_cap_pct=0.10)
    total = sum(float(b["stake_gbp"]) for b in result)
    assert total <= 1000.0 * 0.10 + 0.01  # penny tolerance


def test_per_day_cap_bets_under_limit_all_approved():
    """When total stakes well under cap, all bets pass unchanged."""
    bets = [
        _bet("f1", "ou_2.5", "over", 5.0),
        _bet("f2", "ou_2.5", "over", 5.0),
    ]
    result = portfolio_caps(bets, bankroll=1000.0, per_day_cap_pct=0.10)
    assert len(result) == 2
    assert all(float(b["stake_gbp"]) == 5.0 for b in result)


# ---------------------------------------------------------------------------
# Per-fixture cap
# ---------------------------------------------------------------------------


def test_per_fixture_cap_single_fixture():
    """Two markets on the same fixture cannot exceed fixture cap."""
    bets = [
        _bet("f1", "ou_2.5", "over", 20.0),
        _bet("f1", "btts", "yes", 20.0),
    ]
    result = portfolio_caps(bets, bankroll=1000.0, per_fixture_cap_pct=0.03)
    total_on_f1 = sum(float(b["stake_gbp"]) for b in result if b["fixture_id"] == "f1")
    assert total_on_f1 <= 1000.0 * 0.03 + 0.01


def test_per_fixture_cap_does_not_block_other_fixtures():
    """Per-fixture cap on f1 does not consume f2 headroom."""
    bets = [
        _bet("f1", "ou_2.5", "over", 20.0),
        _bet("f1", "btts", "yes", 20.0),
        _bet("f2", "ou_2.5", "over", 10.0),
    ]
    result = portfolio_caps(bets, bankroll=1000.0, per_day_cap_pct=0.10, per_fixture_cap_pct=0.03)
    f2_bets = [b for b in result if b["fixture_id"] == "f2"]
    assert len(f2_bets) == 1
    assert float(f2_bets[0]["stake_gbp"]) == 10.0


# ---------------------------------------------------------------------------
# Correlated bets (same fixture_id = correlated per §4.2)
# ---------------------------------------------------------------------------


def test_correlated_bets_share_fixture_cap():
    """Over 2.5 + BTTS on same fixture share the 3% fixture cap."""
    bets = [
        _bet("match1", "ou_2.5", "over", 25.0),
        _bet("match1", "btts", "yes", 25.0),
        _bet("match1", "1x2", "home", 25.0),
    ]
    result = portfolio_caps(bets, bankroll=1000.0, per_fixture_cap_pct=0.03, per_day_cap_pct=0.20)
    total_on_match = sum(float(b["stake_gbp"]) for b in result)
    assert total_on_match <= 1000.0 * 0.03 + 0.01


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_zero_stake_candidates_excluded():
    bets = [
        _bet("f1", "ou_2.5", "over", 0.0),
        _bet("f2", "ou_2.5", "over", 10.0),
    ]
    result = portfolio_caps(bets, bankroll=1000.0)
    assert len(result) == 1
    assert result[0]["fixture_id"] == "f2"


def test_empty_candidates_returns_empty():
    assert portfolio_caps([], bankroll=1000.0) == []


def test_output_preserves_extra_fields():
    """Non-stake fields (like odds_quoted) are preserved in output."""
    bets = [
        {
            "fixture_id": "f1",
            "market": "ou_2.5",
            "selection": "over",
            "stake_gbp": Decimal("10.00"),
            "odds_quoted": 2.1,
            "extra_key": "foo",
        }
    ]
    result = portfolio_caps(bets, bankroll=1000.0)
    assert result[0].get("extra_key") == "foo"
    assert result[0]["odds_quoted"] == 2.1


def test_cap_hit_flag_set_when_downsized():
    """portfolio_cap_hit=True when stake is reduced by the cap."""
    bets = [
        _bet("f1", "ou_2.5", "over", 100.0),  # well above 3% = £30
    ]
    result = portfolio_caps(bets, bankroll=1000.0, per_fixture_cap_pct=0.03)
    assert result[0]["portfolio_cap_hit"] is True


def test_no_cap_hit_when_stake_within_limits():
    """portfolio_cap_hit=False when stake is within all caps."""
    bets = [_bet("f1", "ou_2.5", "over", 5.0)]
    result = portfolio_caps(bets, bankroll=1000.0, per_day_cap_pct=0.10, per_fixture_cap_pct=0.03)
    assert result[0]["portfolio_cap_hit"] is False
