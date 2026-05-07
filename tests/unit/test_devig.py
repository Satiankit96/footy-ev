"""Unit tests for de-vig methods."""

from __future__ import annotations

import pytest

from footy_ev.eval.devig import devig, devig_power, devig_shin


def test_devig_shin_threeway_sums_to_one():
    q = devig_shin((1.5, 4.0, 5.0))
    assert sum(q) == pytest.approx(1.0, abs=1e-9)
    assert all(p > 0 for p in q)


def test_devig_power_threeway_sums_to_one():
    q = devig_power((1.5, 4.0, 5.0))
    assert sum(q) == pytest.approx(1.0, abs=1e-9)
    assert all(p > 0 for p in q)


def test_devig_no_vig_passthrough():
    """Odds with sum(1/o) == 1 (no margin) yield ~ original probabilities."""
    # Construct a no-vig 3-way: probs 0.5/0.3/0.2 → odds 2.0, 10/3, 5.0
    odds = (2.0, 10.0 / 3.0, 5.0)
    raw_pi = tuple(1.0 / o for o in odds)
    assert sum(raw_pi) == pytest.approx(1.0, abs=1e-9)
    for method in ("shin", "power"):
        q = devig(odds, method=method)  # type: ignore[arg-type]
        assert sum(q) == pytest.approx(1.0, abs=1e-9)
        for raw, calibrated in zip(raw_pi, q, strict=False):
            assert raw == pytest.approx(calibrated, abs=1e-6)


def test_devig_shin_high_overround():
    """Margin ~10% market still de-vigs to a valid probability simplex."""
    odds = (1.45, 4.0, 5.5)  # sum(1/o) ≈ 1.10, ~10% overround
    pi_sum = sum(1.0 / o for o in odds)
    assert pi_sum > 1.05
    q = devig_shin(odds)
    assert sum(q) == pytest.approx(1.0, abs=1e-9)
    assert all(0 < p < 1 for p in q)


def test_devig_preserves_ordering():
    """Both methods must keep argmax(1/o) == argmax(q)."""
    odds = (1.59, 4.40, 5.75)  # PSC sample from Arsenal-Liverpool 2026-01-08
    raw_pi = [1.0 / o for o in odds]
    raw_argmax = raw_pi.index(max(raw_pi))
    for method in ("shin", "power"):
        q = devig(odds, method=method)  # type: ignore[arg-type]
        q_argmax = list(q).index(max(q))
        assert q_argmax == raw_argmax, f"method={method} reorders favorites"


def test_devig_rejects_invalid_odds():
    with pytest.raises(ValueError):
        devig_shin((1.5,))  # too few
    with pytest.raises(ValueError):
        devig_shin((2.0, 1.0, 5.0))  # = 1.0 not allowed
    with pytest.raises(ValueError):
        devig_power((2.0, -3.0, 5.0))  # negative


def test_devig_dispatch():
    """`devig(method='shin')` matches devig_shin; `'power'` matches devig_power."""
    odds = (1.7, 3.6, 5.0)
    assert devig(odds, method="shin") == devig_shin(odds)
    assert devig(odds, method="power") == devig_power(odds)
    with pytest.raises(ValueError):
        devig(odds, method="bogus")  # type: ignore[arg-type]
