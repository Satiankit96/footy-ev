"""Monte Carlo bankroll ruin simulator per BLUE_MAP §4.3.

Simulates N independent bets under a given edge and Kelly fraction.
Uses a simplified even-money model: each bet wins with p = 0.5 + edge/2
at decimal odds = 2.0, so full Kelly fraction = edge.

At kelly_fraction of full Kelly, each bet stakes kelly_fraction * edge
of the current bankroll.
"""

from __future__ import annotations

import numpy as np


def simulate_ruin(
    edge_pct: float,
    edge_se: float,
    kelly_fraction: float,
    n_bets: int = 1_000,
    n_sims: int = 10_000,
    rng_seed: int = 0,
) -> dict[str, float | list[float]]:
    """Monte Carlo ruin simulation with uncertain edge.

    Each simulation:
      1. Draws a "realised edge" from N(edge_pct, edge_se) — captures
         the uncertainty about whether the backtested edge is real.
      2. Simulates n_bets binary bets with that realised edge at
         kelly_fraction of full Kelly (even-money model).
      3. Tracks the bankroll trajectory to compute drawdown metrics.

    Args:
        edge_pct: expected mean edge (e.g. 0.0108 for 1.08% edge).
        edge_se: standard error of the edge estimate.
        kelly_fraction: fraction of full Kelly to stake (e.g. 0.25).
        n_bets: number of bets per simulation.
        n_sims: number of Monte Carlo draws.
        rng_seed: for reproducibility.

    Returns:
        Dict with:
          p_50pct_drawdown         fraction of sims that touched ≤50% of peak bankroll.
          p_below_50pct_after_1000 fraction of sims ending below 50% starting bankroll.
          max_drawdown_p95         95th-percentile max drawdown fraction (0–1 scale).
          final_bankroll_mean      mean terminal bankroll (starting = 1.0).
          final_bankroll_p10       10th-percentile terminal bankroll.
          final_bankroll_p50       median terminal bankroll.
          final_bankroll_p90       90th-percentile terminal bankroll.
          final_bankroll_dist      list of n_sims terminal bankrolls (for histograms).
    """
    rng = np.random.default_rng(rng_seed)

    # Draw realised edge for each simulation
    realised_edges = rng.normal(edge_pct, edge_se, size=n_sims)

    # For even-money bets: p_win = 0.5 + edge/2; full Kelly fraction = edge
    # Stake per bet = kelly_fraction * edge * bankroll
    # Win payoff: +stake; loss: -stake (even money)

    touched_50pct = 0
    below_50pct_final = 0
    max_drawdowns: list[float] = []
    final_bankrolls: list[float] = []

    for edge_i in realised_edges:
        p_win = 0.5 + max(0.0, edge_i) / 2.0
        # Full Kelly for even money: f* = edge_i (= 2p - 1 at b=1)
        f_full = max(0.0, edge_i)
        f_stake = kelly_fraction * f_full  # fraction of bankroll staked each bet

        bankroll = 1.0
        peak = 1.0
        max_dd = 0.0
        hit_50 = False

        # Vectorized: draw all outcomes at once
        outcomes = rng.uniform(size=n_bets) < p_win  # True = win

        for win in outcomes:
            if f_stake <= 0.0:
                break
            stake_abs = f_stake * bankroll
            bankroll = bankroll + stake_abs if win else bankroll - stake_abs
            bankroll = max(bankroll, 0.0)
            if bankroll > peak:
                peak = bankroll
            dd = (peak - bankroll) / peak if peak > 0.0 else 0.0
            if dd > max_dd:
                max_dd = dd
            if bankroll <= 0.5:
                hit_50 = True

        if hit_50:
            touched_50pct += 1
        if bankroll < 0.5:
            below_50pct_final += 1
        max_drawdowns.append(max_dd)
        final_bankrolls.append(bankroll)

    arr = np.array(final_bankrolls, dtype=float)
    dd_arr = np.array(max_drawdowns, dtype=float)

    return {
        "p_50pct_drawdown": touched_50pct / n_sims,
        "p_below_50pct_after_1000": below_50pct_final / n_sims,
        "max_drawdown_p95": float(np.percentile(dd_arr, 95)),
        "final_bankroll_mean": float(arr.mean()),
        "final_bankroll_p10": float(np.percentile(arr, 10)),
        "final_bankroll_p50": float(np.percentile(arr, 50)),
        "final_bankroll_p90": float(np.percentile(arr, 90)),
        "final_bankroll_dist": arr.tolist(),
    }


if __name__ == "__main__":
    result = simulate_ruin(0.05, 0.02, 0.25, n_bets=1000, n_sims=1000, rng_seed=0)
    print(f"p(50% drawdown)   = {result['p_50pct_drawdown']:.3f}")
    print(f"p(below 50% @ end)= {result['p_below_50pct_after_1000']:.3f}")
    print(f"max DD p95        = {result['max_drawdown_p95']:.3f}")
    print(f"final B median    = {result['final_bankroll_p50']:.3f}")
    print("smoke: OK")
