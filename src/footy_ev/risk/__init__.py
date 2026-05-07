"""Risk and bankroll management module.

Exports:
    kelly_stake       — fractional Kelly stake with uncertainty shrinkage (BLUE_MAP §4.1)
    kelly_fraction_used — fraction of bankroll used (no bankroll arg)
    portfolio_caps    — per-day / per-fixture / correlation caps (BLUE_MAP §4.2)
    simulate_ruin     — Monte Carlo ruin simulation (BLUE_MAP §4.3)
"""

from footy_ev.risk.kelly import kelly_fraction_used, kelly_stake
from footy_ev.risk.portfolio import portfolio_caps
from footy_ev.risk.ruin import simulate_ruin

__all__ = [
    "kelly_stake",
    "kelly_fraction_used",
    "portfolio_caps",
    "simulate_ruin",
]
