"""Dixon-Coles bivariate-Poisson model for football match scores.

References:
  Dixon, M. J., & Coles, S. G. (1997). "Modelling Association Football Scores
  and Inefficiencies in the Football Betting Market." Applied Statistics 46(2),
  pp. 265-280.

  The tau adjustment for low-scoring matches (eq. 4 in the paper) is:

      tau(x, y; lambda, mu, rho) =
          1 - lambda*mu*rho      if (x, y) == (0, 0)
          1 + lambda*rho         if (x, y) == (0, 1)
          1 + mu*rho             if (x, y) == (1, 0)
          1 - rho                if (x, y) == (1, 1)
          1                      otherwise

  with the parameter constraint
    max(-1/lambda, -1/mu) <= rho <= min(1/lambda, 1/mu).

Parameterization (log-additive form):
    log(lambda_home) = alpha_home - beta_away + gamma_home_adv
    log(mu_away)     = alpha_away - beta_home

  with sum(alpha) = 0 enforced for identifiability (the joint shift
  indeterminacy between alpha and beta is broken by anchoring alpha to
  zero-mean).

All datetimes in this module are NAIVE Python datetime objects, interpreted
as UTC by convention. This matches DuckDB's TIMESTAMP column return type and
avoids aware/naive comparison errors at module boundaries.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import polars as pl
from scipy.optimize import minimize
from scipy.special import gammaln


@dataclass(frozen=True)
class DCFit:
    """Fitted Dixon-Coles parameters and metadata.

    Attributes:
        team_attack: alpha_i per team_id; sum constrained to 0.
        team_defense: beta_i per team_id; level absorbed into gamma.
        gamma_home_adv: log-additive home advantage scalar.
        rho_tau: dependence parameter for the tau low-score adjustment.
        xi_decay: time-decay rate (per day); 0.0 = uniform weights.
        log_likelihood: total log-likelihood at the optimum.
        n_train_matches: number of matches retained after PIT filter.
        as_of: PIT cutoff used during fitting (naive UTC).
        optimizer_status: scipy.optimize.OptimizeResult.message.
        fit_seconds: wall time of the fit.
    """

    team_attack: dict[str, float]
    team_defense: dict[str, float]
    gamma_home_adv: float
    rho_tau: float
    xi_decay: float
    log_likelihood: float
    n_train_matches: int
    as_of: datetime
    optimizer_status: str
    fit_seconds: float


_REQUIRED_COLS = (
    "home_team_id",
    "away_team_id",
    "home_score_ft",
    "away_score_ft",
    "kickoff_utc",
)


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Tau adjustment factor from Dixon-Coles 1997 eq. 4.

    Args:
        x: home goals.
        y: away goals.
        lam: home Poisson rate.
        mu: away Poisson rate.
        rho: dependence parameter.

    Returns:
        Multiplicative factor on the joint Poisson density.
    """
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _validate_matches(matches: pl.DataFrame, as_of: datetime) -> pl.DataFrame:
    """Validate schema and apply the PIT filter (kickoff_utc < as_of).

    Args:
        matches: input training frame.
        as_of: cutoff; rows with kickoff_utc >= as_of are dropped.

    Returns:
        Filtered DataFrame with only finalized, in-window matches.

    Raises:
        ValueError: if required columns are missing.
    """
    missing = set(_REQUIRED_COLS) - set(matches.columns)
    if missing:
        raise ValueError(f"matches missing required columns: {sorted(missing)}")
    return matches.filter(
        (pl.col("kickoff_utc") < as_of)
        & pl.col("home_score_ft").is_not_null()
        & pl.col("away_score_ft").is_not_null()
    )


def log_likelihood(
    matches: pl.DataFrame,
    team_attack: dict[str, float],
    team_defense: dict[str, float],
    gamma_home_adv: float,
    rho_tau: float,
    xi_decay: float,
    *,
    as_of: datetime,
) -> float:
    """Total time-weighted log-likelihood under Dixon-Coles.

    Each match contributes:
        weight_i * (log tau(x_i, y_i; lam_i, mu_i, rho)
                    + log P(x_i; lam_i) + log P(y_i; mu_i))

    where weight_i = exp(-xi_decay * (as_of - kickoff_utc_i).days). For
    xi_decay = 0.0 all weights are 1.0.

    The xi_decay reference timestamp is `as_of`, NOT max(kickoff_utc) of the
    input frame. Snooping the dataset max is a classic Dixon-Coles backtest
    leakage trap; this function pins the reference at the cutoff.

    Args:
        matches: Polars DataFrame with home_team_id, away_team_id,
            home_score_ft, away_score_ft, kickoff_utc.
        team_attack: alpha per team_id.
        team_defense: beta per team_id.
        gamma_home_adv: home advantage.
        rho_tau: tau dependence parameter.
        xi_decay: time-decay rate per day.
        as_of: PIT cutoff (naive UTC). Rows with kickoff_utc >= as_of are
            excluded; rows with team_ids absent from team_attack are skipped.

    Returns:
        Total log-likelihood. Returns 0.0 if no rows remain after filtering.
    """
    df = _validate_matches(matches, as_of)
    if df.height == 0:
        return 0.0

    home_ids = df["home_team_id"].to_list()
    away_ids = df["away_team_id"].to_list()
    home_goals = df["home_score_ft"].to_list()
    away_goals = df["away_score_ft"].to_list()
    kickoffs = df["kickoff_utc"].to_list()

    total = 0.0
    for h, a, x, y, t in zip(home_ids, away_ids, home_goals, away_goals, kickoffs, strict=False):
        if h not in team_attack or a not in team_attack:
            continue
        if h not in team_defense or a not in team_defense:
            continue
        log_lam = team_attack[h] - team_defense[a] + gamma_home_adv
        log_mu = team_attack[a] - team_defense[h]
        lam = math.exp(log_lam)
        mu = math.exp(log_mu)
        tau = _tau(int(x), int(y), lam, mu, rho_tau)
        if tau <= 0.0:
            return -1e18
        log_p_x = x * log_lam - lam - math.lgamma(x + 1)
        log_p_y = y * log_mu - mu - math.lgamma(y + 1)
        per_match = math.log(tau) + log_p_x + log_p_y
        if xi_decay > 0.0:
            delta_days = (as_of - t).total_seconds() / 86400.0
            per_match *= math.exp(-xi_decay * delta_days)
        total += per_match
    return total


def fit(
    matches: pl.DataFrame,
    *,
    as_of: datetime,
    xi_decay: float = 0.0019,
    rng_seed: int = 0,
) -> DCFit:
    """Fit Dixon-Coles by maximum likelihood with L-BFGS-B.

    Parameter vector layout for scipy:
        [alpha_1, ..., alpha_{N-1}, beta_1, ..., beta_N, gamma, rho]
    where alpha_N is reconstructed as -sum(alpha_1..N-1) to enforce the
    zero-mean attack constraint.

    Args:
        matches: training matches; must satisfy log_likelihood schema.
        as_of: PIT cutoff (naive UTC). Matches with kickoff_utc >= as_of
            are dropped before fitting.
        xi_decay: time-decay rate per day; 0.0 = uniform weights. Reference
            timestamp for decay is `as_of` (per leakage trap above).
        rng_seed: seed for parameter initialization perturbation.

    Returns:
        DCFit with optimized parameters.

    Raises:
        ValueError: if the filtered match set is empty or has fewer than
            two distinct teams.
    """
    df = _validate_matches(matches, as_of)
    if df.height == 0:
        raise ValueError("no training matches after PIT filter")

    teams = sorted(set(df["home_team_id"].to_list()) | set(df["away_team_id"].to_list()))
    n = len(teams)
    if n < 2:
        raise ValueError(f"need >= 2 distinct teams, got {n}")

    team_idx = {t: i for i, t in enumerate(teams)}
    home_idx = np.array([team_idx[h] for h in df["home_team_id"].to_list()], dtype=int)
    away_idx = np.array([team_idx[a] for a in df["away_team_id"].to_list()], dtype=int)
    home_goals = np.array(df["home_score_ft"].to_list(), dtype=int)
    away_goals = np.array(df["away_score_ft"].to_list(), dtype=int)
    kickoffs = df["kickoff_utc"].to_list()

    if xi_decay > 0.0:
        deltas = np.array([(as_of - t).total_seconds() / 86400.0 for t in kickoffs])
        weights = np.exp(-xi_decay * deltas)
    else:
        weights = np.ones(len(home_idx))

    rng = np.random.default_rng(rng_seed)
    x0_alpha = rng.normal(0.0, 0.05, size=n - 1)
    x0_beta = rng.normal(0.0, 0.05, size=n)
    x0 = np.concatenate([x0_alpha, x0_beta, [0.30, -0.05]])  # gamma~0.30, rho~-0.05

    log_factorial_home = gammaln(home_goals + 1)
    log_factorial_away = gammaln(away_goals + 1)

    m00 = (home_goals == 0) & (away_goals == 0)
    m01 = (home_goals == 0) & (away_goals == 1)
    m10 = (home_goals == 1) & (away_goals == 0)
    m11 = (home_goals == 1) & (away_goals == 1)

    def unpack(
        params: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, float, float]:
        alpha_short = params[: n - 1]
        alpha_full = np.concatenate([alpha_short, [-alpha_short.sum()]])
        beta = params[n - 1 : 2 * n - 1]
        gamma = float(params[2 * n - 1])
        rho = float(params[2 * n])
        return alpha_full, beta, gamma, rho

    def neg_ll(params: np.ndarray) -> float:
        alpha, beta, gamma, rho = unpack(params)
        log_lam = alpha[home_idx] - beta[away_idx] + gamma
        log_mu = alpha[away_idx] - beta[home_idx]
        lam = np.exp(log_lam)
        mu = np.exp(log_mu)
        tau = np.ones(len(home_idx))
        tau[m00] = 1.0 - lam[m00] * mu[m00] * rho
        tau[m01] = 1.0 + lam[m01] * rho
        tau[m10] = 1.0 + mu[m10] * rho
        tau[m11] = 1.0 - rho
        if np.any(tau <= 0.0):
            return 1e18
        log_p_home = home_goals * log_lam - lam - log_factorial_home
        log_p_away = away_goals * log_mu - mu - log_factorial_away
        per_match = np.log(tau) + log_p_home + log_p_away
        return float(-np.sum(weights * per_match))

    bounds = (
        [(-3.0, 3.0)] * (n - 1)  # alpha_short
        + [(-3.0, 3.0)] * n  # beta
        + [(-1.0, 2.0), (-0.5, 0.5)]  # gamma, rho
    )

    t0 = time.perf_counter()
    result = minimize(neg_ll, x0, method="L-BFGS-B", bounds=bounds)
    fit_seconds = time.perf_counter() - t0

    alpha_full, beta_full, gamma_opt, rho_opt = unpack(result.x)
    return DCFit(
        team_attack={teams[i]: float(alpha_full[i]) for i in range(n)},
        team_defense={teams[i]: float(beta_full[i]) for i in range(n)},
        gamma_home_adv=float(gamma_opt),
        rho_tau=float(rho_opt),
        xi_decay=float(xi_decay),
        log_likelihood=float(-result.fun),
        n_train_matches=int(df.height),
        as_of=as_of,
        optimizer_status=str(result.message),
        fit_seconds=float(fit_seconds),
    )


def predict_1x2(
    fit: DCFit,
    home_team_id: str,
    away_team_id: str,
    *,
    max_goals: int = 10,
) -> tuple[float, float, float]:
    """Predict 1X2 probabilities under Dixon-Coles for a single match.

    Args:
        fit: fitted parameters from `fit()`.
        home_team_id: must exist in fit.team_attack and fit.team_defense.
        away_team_id: must exist in fit.team_attack and fit.team_defense.
        max_goals: truncate score grid at this many goals per side. The
            tail >10 contributes <1e-6 for typical match rates.

    Returns:
        (p_home, p_draw, p_away) summing to 1.0 (renormalized to absorb
        any small numerical drift from the tau adjustment).

    Raises:
        KeyError: if either team_id is unknown to the fit.
    """
    if home_team_id not in fit.team_attack:
        raise KeyError(f"unknown home_team_id: {home_team_id}")
    if away_team_id not in fit.team_attack:
        raise KeyError(f"unknown away_team_id: {away_team_id}")
    log_lam = fit.team_attack[home_team_id] - fit.team_defense[away_team_id] + fit.gamma_home_adv
    log_mu = fit.team_attack[away_team_id] - fit.team_defense[home_team_id]
    lam = math.exp(log_lam)
    mu = math.exp(log_mu)

    grid_size = max_goals + 1
    xs = np.arange(grid_size)
    log_pois_x = xs * math.log(lam) - lam - gammaln(xs + 1)
    log_pois_y = xs * math.log(mu) - mu - gammaln(xs + 1)
    pois_x = np.exp(log_pois_x)
    pois_y = np.exp(log_pois_y)

    # grid[x, y] = P(home_goals=x) * P(away_goals=y) * tau(x, y)
    grid = np.outer(pois_x, pois_y)
    grid[0, 0] *= 1.0 - lam * mu * fit.rho_tau
    grid[0, 1] *= 1.0 + lam * fit.rho_tau
    grid[1, 0] *= 1.0 + mu * fit.rho_tau
    grid[1, 1] *= 1.0 - fit.rho_tau

    # Home wins: x > y (strict lower triangle, k=-1)
    p_home = float(grid[np.tril_indices(grid_size, k=-1)].sum())
    p_draw = float(np.diag(grid).sum())
    # Away wins: x < y (strict upper triangle, k=1)
    p_away = float(grid[np.triu_indices(grid_size, k=1)].sum())

    total = p_home + p_draw + p_away
    if total <= 0.0:
        return (1.0 / 3, 1.0 / 3, 1.0 / 3)
    return (p_home / total, p_draw / total, p_away / total)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    base = datetime(2024, 1, 1)
    rows = [
        {
            "home_team_id": "a" if i % 2 == 0 else "b",
            "away_team_id": "b" if i % 2 == 0 else "a",
            "home_score_ft": int(rng.poisson(1.4)),
            "away_score_ft": int(rng.poisson(1.0)),
            "kickoff_utc": datetime(2024, 1, 1 + i),
        }
        for i in range(20)
    ]
    df = pl.DataFrame(rows)
    dc = fit(df, as_of=datetime(2024, 6, 1))
    p = predict_1x2(dc, "a", "b")
    print(
        f"DC smoke: p_home={p[0]:.3f} p_draw={p[1]:.3f} p_away={p[2]:.3f} ll={dc.log_likelihood:.2f}"
    )
