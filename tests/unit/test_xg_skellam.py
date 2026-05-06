"""Unit tests for the xG-Skellam O/U model."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from footy_ev.models.xg_skellam import (
    InsufficientTrainingData,
    fit,
    predict_ou25,
)


def _make_matches(
    n: int,
    *,
    rng_seed: int = 0,
    teams: list[str] | None = None,
    base: datetime | None = None,
    home_xg_mean: float = 1.4,
    away_xg_mean: float = 1.0,
    include_nulls: int = 0,
) -> pl.DataFrame:
    """Synthetic match frame with continuous xG values."""
    if teams is None:
        teams = ["a", "b", "c", "d"]
    if base is None:
        base = datetime(2020, 1, 1)
    rng = np.random.default_rng(rng_seed)
    rows = []
    for i in range(n):
        h = teams[i % len(teams)]
        a = teams[(i + 1) % len(teams)]
        hxg: float | None = float(rng.exponential(home_xg_mean))
        axg: float | None = float(rng.exponential(away_xg_mean))
        if i < include_nulls:
            hxg = None
            axg = None
        rows.append(
            {
                "home_team_id": h,
                "away_team_id": a,
                "home_xg": hxg,
                "away_xg": axg,
                "kickoff_utc": base + timedelta(days=i),
            }
        )
    return pl.DataFrame(rows)


def test_insufficient_training_data_raises():
    """Fewer than min_train_matches xG-complete rows raises InsufficientTrainingData."""
    df = _make_matches(10)
    with pytest.raises(InsufficientTrainingData):
        fit(df, as_of=datetime(2020, 12, 31), min_train_matches=200)


def test_fit_identifiability_zero_mean_attack():
    """Fitted alpha parameters must sum to approximately 0."""
    df = _make_matches(220, rng_seed=42)
    xg = fit(df, as_of=datetime(2021, 1, 1), min_train_matches=200)
    alpha_sum = sum(xg.team_attack.values())
    assert abs(alpha_sum) < 1e-6, f"alpha sum = {alpha_sum:.2e}"


def test_predict_ou25_sums_to_one():
    """p_over + p_under must equal exactly 1.0."""
    df = _make_matches(220, rng_seed=7)
    xg = fit(df, as_of=datetime(2021, 1, 1), min_train_matches=200)
    teams = list(xg.team_attack)
    for h in teams:
        for a in teams:
            if h != a:
                p_over, p_under = predict_ou25(xg, h, a)
                assert p_over + p_under == pytest.approx(1.0, abs=1e-9)
                assert 0.0 <= p_over <= 1.0
                assert 0.0 <= p_under <= 1.0


def test_predict_ou25_unknown_team_raises():
    """KeyError on unknown team_id."""
    df = _make_matches(220)
    xg = fit(df, as_of=datetime(2021, 1, 1), min_train_matches=200)
    with pytest.raises(KeyError):
        predict_ou25(xg, "a", "ghost")
    with pytest.raises(KeyError):
        predict_ou25(xg, "ghost", "b")


def test_fit_pit_filter_excludes_at_cutoff():
    """Rows with kickoff_utc == as_of are excluded (half-open boundary)."""
    base = datetime(2020, 1, 1)
    cutoff = datetime(2020, 9, 1)
    df = _make_matches(230, base=base)
    # Confirm PIT: matches at base+228 days are before cutoff; match at cutoff is excluded.
    df_with_cutoff = pl.concat(
        [
            df,
            pl.DataFrame(
                [
                    {
                        "home_team_id": "a",
                        "away_team_id": "b",
                        "home_xg": 1.0,
                        "away_xg": 0.8,
                        "kickoff_utc": cutoff,  # exactly at cutoff → excluded
                    }
                ]
            ),
        ]
    )
    xg = fit(df_with_cutoff, as_of=cutoff, min_train_matches=10)
    # n_train_matches should not include the at-cutoff row (also filters by xG null)
    # Just verify it runs without raising and the cutoff row is excluded.
    assert xg.n_train_matches <= 230


def test_fit_null_xg_excluded():
    """Rows with NULL home_xg or away_xg are excluded from training."""
    n_total = 220
    n_nulls = 20
    df = _make_matches(n_total, include_nulls=n_nulls)
    # Only the non-null rows should count
    xg = fit(df, as_of=datetime(2021, 1, 1), min_train_matches=100)
    assert xg.n_train_matches == n_total - n_nulls


def test_xi_decay_changes_log_likelihood():
    """Non-zero xi_decay should yield a different (typically higher) log-likelihood than 0."""
    df = _make_matches(220, rng_seed=99)
    as_of = datetime(2021, 1, 1)
    xg_no_decay = fit(df, as_of=as_of, xi_decay=0.0, min_train_matches=100)
    xg_with_decay = fit(df, as_of=as_of, xi_decay=0.0019, min_train_matches=100)
    # Log-likelihoods are computed under different weight schedules → differ.
    assert xg_no_decay.log_likelihood != pytest.approx(xg_with_decay.log_likelihood, rel=1e-4)
