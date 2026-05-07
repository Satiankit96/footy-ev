"""Reliability binning for probability calibration evaluation.

Per BLUE_MAP §7.5: a well-calibrated model's predicted probabilities, when
binned, should match observed frequencies bin by bin. This module produces
the bin-level statistics; plotting lives in a notebook (Matplotlib-free
here per project convention — keeps imports lean and tests headless).

Acceptance criterion (BLUE_MAP §7.5): every populated bin's observed
frac_pos within ±2 percentage points of mean predicted probability. We
record the per-bin pass flag and let the report layer aggregate.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import polars as pl

DEFAULT_N_BINS = 15
ACCEPTANCE_TOLERANCE = 0.02  # ±2 pp


def reliability_bins(
    p_calibrated: Sequence[float],
    is_winner: Sequence[bool],
    *,
    n_bins: int = DEFAULT_N_BINS,
) -> pl.DataFrame:
    """Compute per-bin reliability stats for a calibrated probability column.

    Bins are uniform on [0, 1]. The last bin is closed on the right
    (`p == 1.0` falls in the final bin); all others are half-open
    (`[lower, upper)`).

    Args:
        p_calibrated: predicted (calibrated) probabilities, length N.
        is_winner: realized binary outcomes, length N.
        n_bins: number of uniform bins.

    Returns:
        Polars DataFrame with one row per bin and columns:
            bin_idx, bin_lower, bin_upper, n_in_bin,
            frac_pos, mean_pred, passes_2pp.
        Empty bins emit n_in_bin=0 with NULL frac_pos / mean_pred /
        passes_2pp.

    Raises:
        ValueError: if input arrays are different lengths or n_bins < 1.
    """
    p_arr = np.asarray(p_calibrated, dtype=float)
    y_arr = np.asarray(is_winner, dtype=bool)
    if p_arr.shape != y_arr.shape:
        raise ValueError(f"length mismatch: p={p_arr.shape}, y={y_arr.shape}")
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        mask = (p_arr >= lo) & (p_arr <= hi) if i == n_bins - 1 else (p_arr >= lo) & (p_arr < hi)
        n = int(mask.sum())
        if n == 0:
            rows.append(
                {
                    "bin_idx": i,
                    "bin_lower": lo,
                    "bin_upper": hi,
                    "n_in_bin": 0,
                    "frac_pos": None,
                    "mean_pred": None,
                    "passes_2pp": None,
                }
            )
        else:
            frac = float(y_arr[mask].mean())
            mean_p = float(p_arr[mask].mean())
            passes = bool(abs(frac - mean_p) <= ACCEPTANCE_TOLERANCE)
            rows.append(
                {
                    "bin_idx": i,
                    "bin_lower": lo,
                    "bin_upper": hi,
                    "n_in_bin": n,
                    "frac_pos": frac,
                    "mean_pred": mean_p,
                    "passes_2pp": passes,
                }
            )
    return pl.DataFrame(rows)


def reliability_pass_pct(bins_df: pl.DataFrame) -> float:
    """Percentage of populated bins (n_in_bin > 0) that pass ±2pp.

    Returns 0.0 if no populated bins exist.
    """
    populated = bins_df.filter(pl.col("n_in_bin") > 0)
    if populated.height == 0:
        return 0.0
    n_pass = int(populated["passes_2pp"].sum())
    return 100.0 * n_pass / populated.height
