"""Unit tests for reliability binning."""

from __future__ import annotations

import numpy as np
import pytest

from footy_ev.eval.reliability import reliability_bins, reliability_pass_pct


def test_reliability_well_calibrated_input_passes():
    """Realizations drawn from y ~ Bernoulli(p) — every populated bin
    should pass ±2pp under a sample large enough that bin SE is small."""
    rng = np.random.default_rng(123)
    n = 30_000
    p = rng.uniform(0.05, 0.95, size=n)
    y = rng.binomial(1, p).astype(bool)
    bins = reliability_bins(p, y, n_bins=15)
    # Drop empty bins
    populated = bins.filter(bins["n_in_bin"] > 0)
    assert populated.height >= 12, "expect most of 15 bins populated"
    # 30k samples / 15 bins = 2k per bin; SE ~ sqrt(0.25/2000) ≈ 0.011 → ±2pp safe
    assert all(populated["passes_2pp"].to_list())


def test_reliability_miscalibrated_input_fails():
    """Inflate predicted prob by +0.10 — every populated bin should fail."""
    rng = np.random.default_rng(7)
    n = 5_000
    true_p = rng.uniform(0.10, 0.80, size=n)
    y = rng.binomial(1, true_p).astype(bool)
    p_inflated = np.clip(true_p + 0.10, 0.0, 1.0)
    bins = reliability_bins(p_inflated, y, n_bins=15)
    populated = bins.filter(bins["n_in_bin"] > 0)
    # All populated bins should miscalibrate by ~0.10 → all FAIL
    assert not any(populated["passes_2pp"].to_list())


def test_reliability_empty_bins_yield_null():
    """A bin with no predictions yields n_in_bin=0 and NULL stats — no division by zero."""
    p = np.array([0.05, 0.06, 0.95, 0.96])
    y = np.array([False, True, True, False])
    bins = reliability_bins(p, y, n_bins=10)
    # Most middle bins (0.1..0.9) are empty
    empty_rows = bins.filter(bins["n_in_bin"] == 0)
    assert empty_rows.height >= 6
    for r in empty_rows.iter_rows(named=True):
        assert r["frac_pos"] is None
        assert r["mean_pred"] is None
        assert r["passes_2pp"] is None


def test_reliability_pass_pct_excludes_empty_bins():
    """pass_pct denominator counts populated bins only."""
    rng = np.random.default_rng(0)
    n = 4_000
    p = rng.uniform(0.4, 0.6, size=n)  # narrow band → many empty bins
    y = rng.binomial(1, p).astype(bool)
    bins = reliability_bins(p, y, n_bins=15)
    populated = bins.filter(bins["n_in_bin"] > 0)
    pct = reliability_pass_pct(bins)
    assert 0.0 <= pct <= 100.0
    assert populated.height >= 1


def test_reliability_pass_pct_zero_when_no_data():
    bins = reliability_bins(np.array([], dtype=float), np.array([], dtype=bool))
    assert reliability_pass_pct(bins) == 0.0


def test_reliability_input_length_mismatch_raises():
    with pytest.raises(ValueError):
        reliability_bins([0.1, 0.2, 0.3], [True, False])


def test_reliability_p_at_one_lands_in_last_bin():
    """p == 1.0 should be in the final bin (closed-right boundary)."""
    p = np.array([1.0])
    y = np.array([True])
    bins = reliability_bins(p, y, n_bins=10)
    last = bins.filter(bins["bin_idx"] == 9)
    assert last["n_in_bin"][0] == 1
