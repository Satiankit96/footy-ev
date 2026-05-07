"""Unit tests for the Dixon-Coles model.

All datetimes are NAIVE (no tzinfo) to match the module's convention and
DuckDB's TIMESTAMP return type.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from footy_ev.models.dixon_coles import (
    DCFit,
    _tau,
    fit,
    log_likelihood,
    predict_1x2,
)

# -------------------------------------------------------------------------
# Tau adjustment (Dixon-Coles 1997 eq. 4)
# -------------------------------------------------------------------------


def test_tau_zero_zero():
    assert _tau(0, 0, 1.5, 1.2, -0.1) == pytest.approx(1.0 - 1.5 * 1.2 * (-0.1))


def test_tau_zero_one():
    assert _tau(0, 1, 1.5, 1.2, -0.1) == pytest.approx(1.0 + 1.5 * (-0.1))


def test_tau_one_zero():
    assert _tau(1, 0, 1.5, 1.2, -0.1) == pytest.approx(1.0 + 1.2 * (-0.1))


def test_tau_one_one():
    assert _tau(1, 1, 1.5, 1.2, -0.1) == pytest.approx(1.0 - (-0.1))


def test_tau_other_unity():
    for x, y in [(2, 1), (3, 3), (0, 4), (5, 0), (2, 0), (0, 2), (1, 2), (2, 1)]:
        assert _tau(x, y, 1.5, 1.2, -0.1) == 1.0


# -------------------------------------------------------------------------
# predict_1x2: probabilities sum to 1, non-negative, raises on unknown teams
# -------------------------------------------------------------------------


def _zero_mean(d: dict[str, float]) -> dict[str, float]:
    m = sum(d.values()) / len(d)
    return {k: v - m for k, v in d.items()}


def _make_fit(
    teams: list[str],
    attack: dict[str, float],
    defense: dict[str, float],
    gamma: float,
    rho: float,
) -> DCFit:
    return DCFit(
        team_attack=attack,
        team_defense=defense,
        gamma_home_adv=gamma,
        rho_tau=rho,
        xi_decay=0.0,
        log_likelihood=0.0,
        n_train_matches=0,
        as_of=datetime(2024, 1, 1),
        optimizer_status="test",
        fit_seconds=0.0,
    )


def test_predict_1x2_sums_to_one_random():
    rng = np.random.default_rng(42)
    teams = ["a", "b", "c"]
    for _ in range(10):
        attack = _zero_mean({t: float(rng.normal(0, 0.3)) for t in teams})
        defense = {t: float(rng.normal(0, 0.3)) for t in teams}
        gamma = float(rng.normal(0.3, 0.1))
        rho = float(rng.uniform(-0.15, 0.05))
        dc = _make_fit(teams, attack, defense, gamma, rho)
        p_h, p_d, p_a = predict_1x2(dc, "a", "b")
        assert p_h + p_d + p_a == pytest.approx(1.0, abs=1e-9)
        assert p_h >= 0 and p_d >= 0 and p_a >= 0


def test_predict_1x2_unknown_team_raises():
    teams = ["a", "b"]
    dc = _make_fit(
        teams,
        attack={"a": 0.0, "b": 0.0},
        defense={"a": 0.0, "b": 0.0},
        gamma=0.3,
        rho=-0.05,
    )
    with pytest.raises(KeyError):
        predict_1x2(dc, "a", "ghost")
    with pytest.raises(KeyError):
        predict_1x2(dc, "ghost", "b")


# -------------------------------------------------------------------------
# Toy 4-team round-robin: known-good log-likelihood
# -------------------------------------------------------------------------


def _toy_4team_matches() -> pl.DataFrame:
    """4-team round-robin (12 ordered matches), scores hand-set to cover
    every tau case (0,0), (0,1), (1,0), (1,1) and several non-adjusted cells.
    """
    teams = ["alpha", "bravo", "charlie", "delta"]
    base_date = datetime(2024, 1, 1, 15)
    scores = [
        ("alpha", "bravo", 2, 1),
        ("alpha", "charlie", 0, 0),  # tau (0,0)
        ("alpha", "delta", 3, 0),
        ("bravo", "alpha", 1, 1),  # tau (1,1)
        ("bravo", "charlie", 1, 0),  # tau (1,0)
        ("bravo", "delta", 2, 2),
        ("charlie", "alpha", 0, 1),  # tau (0,1)
        ("charlie", "bravo", 0, 2),
        ("charlie", "delta", 1, 1),  # tau (1,1)
        ("delta", "alpha", 1, 4),
        ("delta", "bravo", 0, 3),
        ("delta", "charlie", 2, 2),
    ]
    rows = []
    for i, (h, a, hs, asg) in enumerate(scores):
        rows.append(
            {
                "home_team_id": h,
                "away_team_id": a,
                "home_score_ft": hs,
                "away_score_ft": asg,
                "kickoff_utc": base_date + timedelta(days=i),
            }
        )
    _ = teams  # keep `teams` named for documentation purposes
    return pl.DataFrame(rows)


def test_log_likelihood_known_good():
    """LL at fixed params equals an independently summed value (xi=0)."""
    df = _toy_4team_matches()
    teams = sorted(set(df["home_team_id"].to_list()) | set(df["away_team_id"].to_list()))
    attack = dict.fromkeys(teams, 0.0)
    defense = dict.fromkeys(teams, 0.0)
    gamma = 0.25
    rho = -0.10
    cutoff = datetime(2025, 1, 1)

    expected = 0.0
    for r in df.iter_rows(named=True):
        x, y = int(r["home_score_ft"]), int(r["away_score_ft"])
        log_lam = attack[r["home_team_id"]] - defense[r["away_team_id"]] + gamma
        log_mu = attack[r["away_team_id"]] - defense[r["home_team_id"]]
        lam = math.exp(log_lam)
        mu = math.exp(log_mu)
        tau = _tau(x, y, lam, mu, rho)
        log_p_x = x * log_lam - lam - math.lgamma(x + 1)
        log_p_y = y * log_mu - mu - math.lgamma(y + 1)
        expected += math.log(tau) + log_p_x + log_p_y

    actual = log_likelihood(df, attack, defense, gamma, rho, 0.0, as_of=cutoff)
    assert actual == pytest.approx(expected, abs=1e-9)


# -------------------------------------------------------------------------
# fit() recovery on simulated data
# -------------------------------------------------------------------------


def test_fit_recovers_params_on_simulated():
    """Simulate matches from known params; MLE recovers within tolerance."""
    rng = np.random.default_rng(7)
    teams = ["a", "b", "c", "d"]
    true_attack = {"a": 0.4, "b": 0.1, "c": -0.2, "d": -0.3}
    true_defense = {"a": -0.2, "b": 0.0, "c": 0.1, "d": 0.1}
    true_gamma = 0.3

    rows = []
    base = datetime(2020, 1, 1)
    idx = 0
    for _cycle in range(8):  # 8 cycles × 12 ordered pairs = 96 matches
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                lam = math.exp(true_attack[h] - true_defense[a] + true_gamma)
                mu = math.exp(true_attack[a] - true_defense[h])
                hs = int(rng.poisson(lam))
                asg = int(rng.poisson(mu))
                rows.append(
                    {
                        "home_team_id": h,
                        "away_team_id": a,
                        "home_score_ft": hs,
                        "away_score_ft": asg,
                        "kickoff_utc": base + timedelta(days=idx),
                    }
                )
                idx += 1
    df = pl.DataFrame(rows)
    cutoff = base + timedelta(days=idx + 1)

    dc = fit(df, as_of=cutoff, rng_seed=0)

    # Generous tolerance: small N, Poisson noise, simulator ignores the tau
    # structure (no rho in DGP).
    for t in teams:
        assert abs(dc.team_attack[t] - true_attack[t]) < 0.40, (
            f"alpha[{t}]={dc.team_attack[t]:.3f} vs true {true_attack[t]:.3f}"
        )
    assert abs(dc.gamma_home_adv - true_gamma) < 0.30
    # Identifiability: alpha sum constrained to ~0
    assert abs(sum(dc.team_attack.values())) < 1e-6


# -------------------------------------------------------------------------
# Point-in-time discipline
# -------------------------------------------------------------------------


def test_fit_pit_filter_excludes_at_cutoff():
    """Half-open boundary: kickoff_utc == as_of is EXCLUDED from training."""
    base = datetime(2024, 6, 1)
    df = pl.DataFrame(
        [
            {  # exactly at cutoff -> excluded
                "home_team_id": "a",
                "away_team_id": "b",
                "home_score_ft": 1,
                "away_score_ft": 0,
                "kickoff_utc": base,
            },
            {  # one microsecond before -> included
                "home_team_id": "b",
                "away_team_id": "a",
                "home_score_ft": 0,
                "away_score_ft": 1,
                "kickoff_utc": base - timedelta(microseconds=1),
            },
            {  # well before -> included
                "home_team_id": "a",
                "away_team_id": "b",
                "home_score_ft": 2,
                "away_score_ft": 1,
                "kickoff_utc": base - timedelta(days=1),
            },
        ]
    )
    dc = fit(df, as_of=base, rng_seed=0)
    assert dc.n_train_matches == 2


def test_xi_decay_default_is_0019():
    """fit() default xi_decay should be 0.0019 (Dixon-Coles 1997 EPL-fitted value)."""
    import inspect

    sig = inspect.signature(fit)
    default = sig.parameters["xi_decay"].default
    assert default == pytest.approx(0.0019)


def test_xi_decay_weight_matches_paper_formula():
    """exp(-xi*delta) with xi=0.0019 and delta=365 days gives ~0.50 (half-life ≈ 1 year)."""
    import math

    xi = 0.0019
    delta_days = 365.0
    w = math.exp(-xi * delta_days)
    # paper-motivated: 1-year-old match is weighted ~50%; accept 40-60% range
    assert 0.40 < w < 0.60


def test_xi_decay_no_dataset_max_leakage():
    """Time-decay weights must reference `as_of`, not max(kickoff_utc).

    Pins the canonical Dixon-Coles backtest leakage trap. If the
    implementation snooped max(t) of the input frame, log_likelihood on a
    head-truncated subset would re-anchor the weight clock and yield a
    different per-match weight schedule than computing it directly against
    the same `as_of`.
    """
    base = datetime(2020, 1, 1)
    cutoff = datetime(2024, 1, 1)
    rng = np.random.default_rng(11)
    rows = []
    for i in range(40):
        rows.append(
            {
                "home_team_id": "a" if i % 2 == 0 else "b",
                "away_team_id": "b" if i % 2 == 0 else "a",
                "home_score_ft": int(rng.poisson(1.5)),
                "away_score_ft": int(rng.poisson(1.0)),
                "kickoff_utc": base + timedelta(days=i * 7),
            }
        )
    df = pl.DataFrame(rows)
    attack = {"a": 0.1, "b": -0.1}
    defense = {"a": 0.0, "b": 0.0}
    gamma = 0.3
    rho = -0.05
    xi = 0.005

    df_half = df.head(20)
    ll_half = log_likelihood(df_half, attack, defense, gamma, rho, xi, as_of=cutoff)

    expected = 0.0
    for r in df_half.iter_rows(named=True):
        x, y = int(r["home_score_ft"]), int(r["away_score_ft"])
        log_lam = attack[r["home_team_id"]] - defense[r["away_team_id"]] + gamma
        log_mu = attack[r["away_team_id"]] - defense[r["home_team_id"]]
        lam = math.exp(log_lam)
        mu = math.exp(log_mu)
        tau = _tau(x, y, lam, mu, rho)
        delta_days = (cutoff - r["kickoff_utc"]).total_seconds() / 86400.0
        weight = math.exp(-xi * delta_days)
        log_p_x = x * log_lam - lam - math.lgamma(x + 1)
        log_p_y = y * log_mu - mu - math.lgamma(y + 1)
        expected += weight * (math.log(tau) + log_p_x + log_p_y)

    assert ll_half == pytest.approx(expected, abs=1e-9)
