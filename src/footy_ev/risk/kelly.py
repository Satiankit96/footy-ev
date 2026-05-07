"""Fractional Kelly staking with model uncertainty.

Formula from BLUE_MAP §4.1 — three stacked adjustments:
  1. Lower-bound win probability by uncertainty: p_lb = p_hat - k * sigma_p
  2. Full Kelly on p_lb: f_full = (b * p_lb - q) / b
  3. Fractional Kelly with CLV-aware shrinkage: f_used = base_fraction * clv_multiplier * f_full
  4. Hard per-bet cap: f_used = min(f_used, per_bet_cap_pct)

Stake returned as decimal.Decimal (CLAUDE.md invariant: no float for money).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_PENNY = Decimal("0.01")


def kelly_stake(
    p_hat: float,
    sigma_p: float,
    odds_decimal: float,
    bankroll: float,
    *,
    base_fraction: float = 0.25,
    uncertainty_k: float = 1.0,
    per_bet_cap_pct: float = 0.02,
    recent_clv_pct: float = 0.0,
) -> Decimal:
    """Compute fractional Kelly stake.

    Args:
        p_hat: calibrated win probability from the model.
        sigma_p: bootstrap standard error of p_hat; 0.0 if unknown.
        odds_decimal: decimal odds (e.g. 2.10).
        bankroll: current bankroll in currency units (float for arithmetic).
        base_fraction: quarter-Kelly default (0.25).
        uncertainty_k: std-dev haircut for p_lb (default 1.0 = 1σ lower bound).
        per_bet_cap_pct: hard cap as fraction of bankroll (default 0.02 = 2%).
        recent_clv_pct: rolling 100-bet CLV pct; positive = edge is live,
            negative = edge deteriorating. Drives CLV multiplier.

    Returns:
        Stake as Decimal, rounded to nearest penny. Returns Decimal("0.00")
        when the edge is zero or negative after uncertainty adjustment.
    """
    # 1. Lower-bound win probability
    p_lb = max(0.0, p_hat - uncertainty_k * sigma_p)

    # 2. Full Kelly on lower-bounded p
    b = odds_decimal - 1.0
    if b <= 0.0 or p_lb <= 0.0:
        return Decimal("0.00")
    q = 1.0 - p_lb
    f_full = (b * p_lb - q) / b
    if f_full <= 0.0:
        return Decimal("0.00")

    # 3. Fractional Kelly with CLV-aware multiplier
    #    recent_clv_pct = 0.05 → multiplier = min(1.0, 0.5 + 0.5) = 1.0  (full base)
    #    recent_clv_pct = 0.0  → multiplier = 0.5                         (half base)
    #    recent_clv_pct < -0.05 → multiplier = 0.4                        (floor)
    clv_multiplier = max(0.4, min(1.0, 0.5 + 10.0 * recent_clv_pct))
    f_used = base_fraction * clv_multiplier * f_full

    # 4. Per-bet hard cap
    f_used = min(f_used, per_bet_cap_pct)

    stake_float = f_used * bankroll
    return Decimal(str(stake_float)).quantize(_PENNY, rounding=ROUND_HALF_UP)


def kelly_fraction_used(
    p_hat: float,
    sigma_p: float,
    odds_decimal: float,
    *,
    base_fraction: float = 0.25,
    uncertainty_k: float = 1.0,
    per_bet_cap_pct: float = 0.02,
    recent_clv_pct: float = 0.0,
) -> float:
    """Return the fraction of bankroll that would be staked (no bankroll needed).

    Useful for logging kelly_fraction_used in bet_sizing_decisions.
    """
    p_lb = max(0.0, p_hat - uncertainty_k * sigma_p)
    b = odds_decimal - 1.0
    if b <= 0.0 or p_lb <= 0.0:
        return 0.0
    q = 1.0 - p_lb
    f_full = (b * p_lb - q) / b
    if f_full <= 0.0:
        return 0.0
    clv_multiplier = max(0.4, min(1.0, 0.5 + 10.0 * recent_clv_pct))
    f_used = base_fraction * clv_multiplier * f_full
    return min(f_used, per_bet_cap_pct)


if __name__ == "__main__":
    # Smoke test
    stake = kelly_stake(0.55, 0.02, 2.1, 1000.0)
    print(f"kelly_stake(p=0.55, σ=0.02, odds=2.1, B=1000) = £{stake}")
    assert isinstance(stake, Decimal), "must return Decimal"
    print("smoke: OK")
