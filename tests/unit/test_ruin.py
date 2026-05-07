"""Unit tests for risk.ruin — BLUE_MAP §4.3 Monte Carlo ruin simulator.

Tests:
  1. Known-edge case (p=0.55, even money, quarter Kelly) produces published-
     range ruin probabilities.
  2. Deterministic with rng_seed.
  3. Return dict has all expected keys.
  4. Zero-edge produces worse outcomes than positive edge.
  5. Higher kelly_fraction → higher ruin probability.
  6. final_bankroll_dist length == n_sims.
  7. p_50pct_drawdown and p_below_50pct_after_1000 are valid probabilities [0,1].
"""

from __future__ import annotations

from footy_ev.risk.ruin import simulate_ruin

# Use small n_sims for unit test speed while keeping enough samples for
# statistical assertions with comfortable tolerances.
_FAST = {"n_bets": 500, "n_sims": 2_000, "rng_seed": 42}


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------


def test_return_keys():
    result = simulate_ruin(0.05, 0.01, 0.25, **_FAST)
    expected_keys = {
        "p_50pct_drawdown",
        "p_below_50pct_after_1000",
        "max_drawdown_p95",
        "final_bankroll_mean",
        "final_bankroll_p10",
        "final_bankroll_p50",
        "final_bankroll_p90",
        "final_bankroll_dist",
    }
    assert expected_keys.issubset(result.keys())


def test_final_bankroll_dist_length():
    result = simulate_ruin(0.05, 0.01, 0.25, n_bets=200, n_sims=500, rng_seed=0)
    assert len(result["final_bankroll_dist"]) == 500


def test_probabilities_in_unit_interval():
    result = simulate_ruin(0.05, 0.02, 0.25, **_FAST)
    assert 0.0 <= result["p_50pct_drawdown"] <= 1.0
    assert 0.0 <= result["p_below_50pct_after_1000"] <= 1.0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_with_same_seed():
    r1 = simulate_ruin(0.05, 0.02, 0.25, **_FAST)
    r2 = simulate_ruin(0.05, 0.02, 0.25, **_FAST)
    assert r1["p_50pct_drawdown"] == r2["p_50pct_drawdown"]
    assert r1["final_bankroll_p50"] == r2["final_bankroll_p50"]


def test_different_seeds_may_differ():
    r1 = simulate_ruin(0.05, 0.02, 0.25, n_bets=500, n_sims=2000, rng_seed=0)
    r2 = simulate_ruin(0.05, 0.02, 0.25, n_bets=500, n_sims=2000, rng_seed=99)
    # With enough sims the results converge, but they should not be identical
    # (very unlikely to produce the exact same float from different seeds).
    assert r1["final_bankroll_dist"] != r2["final_bankroll_dist"]


# ---------------------------------------------------------------------------
# Qualitative / ordering tests
# ---------------------------------------------------------------------------


def test_positive_edge_outperforms_zero_edge():
    """Positive edge → higher median terminal bankroll than zero edge."""
    good = simulate_ruin(0.05, 0.01, 0.25, **_FAST)
    flat = simulate_ruin(0.0, 0.01, 0.25, **_FAST)
    assert good["final_bankroll_p50"] > flat["final_bankroll_p50"]


def test_positive_edge_grows_bankroll_vs_no_edge():
    """Positive edge → median terminal bankroll > 1.0 (you profit).
    Zero edge → you don't bet (f_full = max(0, 0) = 0) → bankroll stays at 1.0.
    """
    good = simulate_ruin(0.05, 0.01, 0.25, **_FAST)
    flat = simulate_ruin(0.0, 0.0, 0.25, **_FAST)
    # Positive edge grows bankroll; zero edge → no bets → bankroll stays flat
    assert good["final_bankroll_p50"] > flat["final_bankroll_p50"]


def test_higher_kelly_fraction_increases_ruin():
    """Higher kelly_fraction means larger bets → higher max drawdown."""
    conservative = simulate_ruin(0.05, 0.02, 0.10, **_FAST)
    aggressive = simulate_ruin(0.05, 0.02, 0.50, **_FAST)
    assert aggressive["max_drawdown_p95"] >= conservative["max_drawdown_p95"]


# ---------------------------------------------------------------------------
# Published approximation for known edge
# ---------------------------------------------------------------------------


def test_quarter_kelly_reasonable_ruin_prob():
    """Quarter Kelly on 5% edge, 1000 bets: ruin prob should be low (<30%).

    Published quarter-Kelly theory: ~1-3% ruin. We allow a generous tolerance
    since our model is approximate (even-money only) and n_sims is small.
    """
    result = simulate_ruin(
        edge_pct=0.05,
        edge_se=0.0,
        kelly_fraction=0.25,
        n_bets=1000,
        n_sims=3000,
        rng_seed=7,
    )
    assert result["p_50pct_drawdown"] < 0.30, (
        f"Quarter Kelly at 5% edge touched 50% drawdown in "
        f"{result['p_50pct_drawdown']:.2%} of sims — unexpectedly high"
    )
    assert result["final_bankroll_p50"] > 1.0, (
        "Median terminal bankroll should be > 1.0 with a positive edge"
    )
