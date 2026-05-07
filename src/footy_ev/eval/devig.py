"""De-vig methods for converting decimal odds to true probabilities.

Two methods supported, both n-way (1X2 calls them with 3 odds, but the
implementations are general):

    devig_shin (default per project convention)
        Shin (1991, 1993) "Optimal betting odds against insider traders,"
        Economic Journal. Models book margin as bookmaker insurance against
        a fraction z of insider traders. For raw inverse-odds pi_i = 1/o_i
        and B = sum(pi_i):

            q_i = (sqrt(z^2 + 4(1-z) * pi_i^2 / B) - z) / (2(1-z))

        z is the unique value in (0, 1) for which sum(q_i) = 1. Solved via
        scipy.optimize.brentq.

    devig_power
        Common community method (William Benter et al). Find k such that
        sum(1/o_i^k) = 1; q_i = 1/o_i^k. Solved via scipy.optimize.brentq.
        Less principled than Shin but simple and ordering-preserving.

Both methods:
  - Return a tuple of de-vigged probabilities summing to 1 within numerical
    tolerance.
  - Preserve the ordering of the input pi_i = 1/o_i ratios.
  - Pass through the raw probabilities (with renormalization) when the
    book has no vig (sum(pi_i) <= 1).

The basic / multiplicative method (q_i = pi_i / sum(pi_j)) is intentionally
NOT exposed — it over-flattens and is known to be inferior to both Shin
and power on real bookmaker data (see Buchdahl, Squares & Sharps).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
from scipy.optimize import brentq

DevigMethod = Literal["shin", "power"]


def _validate_odds(odds: Sequence[float]) -> np.ndarray:
    arr = np.asarray(odds, dtype=float)
    if arr.size < 2:
        raise ValueError(f"need at least 2 odds, got {arr.size}")
    if (arr <= 1.0).any():
        raise ValueError(f"all decimal odds must be > 1, got {odds!r}")
    return arr


def devig_shin(odds: Sequence[float]) -> tuple[float, ...]:
    """Shin de-vig. See module docstring.

    Args:
        odds: decimal odds, all > 1.

    Returns:
        Tuple of de-vigged probabilities, same length as input, summing to 1.
    """
    arr = _validate_odds(odds)
    pi = 1.0 / arr
    B = float(pi.sum())
    if abs(B - 1.0) < 1e-12:
        return tuple(float(x) for x in pi)
    if B < 1.0:
        # Anti-vig (sub-margin); proportional rescale.
        return tuple(float(x) for x in pi / B)

    def q_for_z(z: float) -> np.ndarray:
        return (np.sqrt(z**2 + 4.0 * (1.0 - z) * pi**2 / B) - z) / (2.0 * (1.0 - z))

    def constraint(z: float) -> float:
        return float(q_for_z(z).sum() - 1.0)

    # constraint(0+) = sqrt(B) - 1 > 0; constraint approaches sum(pi^2)/B - 1
    # < 0 as z -> 1. Bracket adaptively.
    z_lo = 1e-12
    z_hi = 0.5
    while constraint(z_hi) > 0.0 and z_hi < 0.9999:
        z_hi = (z_hi + 0.9999) / 2.0
    if constraint(z_hi) >= 0.0:
        # Pathological; fall back to power method (or proportional).
        return tuple(float(x) for x in pi / B)

    z = float(brentq(constraint, z_lo, z_hi, xtol=1e-12))
    q = q_for_z(z)
    return tuple(float(x) for x in q)


def devig_power(odds: Sequence[float]) -> tuple[float, ...]:
    """Power-method (Benter) de-vig. See module docstring.

    Args:
        odds: decimal odds, all > 1.

    Returns:
        Tuple of de-vigged probabilities, same length as input, summing to 1.
    """
    arr = _validate_odds(odds)
    pi = 1.0 / arr
    B = float(pi.sum())
    if abs(B - 1.0) < 1e-12:
        return tuple(float(x) for x in pi)
    if B < 1.0:
        return tuple(float(x) for x in pi / B)

    def constraint(k: float) -> float:
        return float(np.sum(1.0 / arr**k) - 1.0)

    # constraint(1) = B - 1 > 0; sum decreases as k grows (since odds > 1).
    k_lo = 1.0
    k_hi = 2.0
    while constraint(k_hi) > 0.0 and k_hi < 100.0:
        k_hi *= 2.0
    if constraint(k_hi) >= 0.0:
        return tuple(float(x) for x in pi / B)

    k = float(brentq(constraint, k_lo, k_hi, xtol=1e-12))
    q = 1.0 / arr**k
    return tuple(float(x) for x in q)


def devig(
    odds: Sequence[float],
    *,
    method: DevigMethod = "shin",
) -> tuple[float, ...]:
    """Dispatch to devig_shin or devig_power."""
    if method == "shin":
        return devig_shin(odds)
    if method == "power":
        return devig_power(odds)
    raise ValueError(f"unknown devig method: {method!r}")


if __name__ == "__main__":
    sample = (1.59, 4.40, 5.75)  # Arsenal-Liverpool 2026-01-08 PSC
    s = devig_shin(sample)
    p = devig_power(sample)
    print(f"odds {sample}: shin={s}, power={p}, shin_sum={sum(s):.6f}, power_sum={sum(p):.6f}")
