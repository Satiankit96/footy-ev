"""xG-Skellam O/U 2.5 model using Understat per-match expected goals.

Each team's xG is modelled as Poisson with rate:
    log(lam_home) = alpha_home - beta_away + gamma_home_adv
    log(lam_away) = alpha_away - beta_home

Parameters are fitted by Poisson kernel MLE on continuous xG observations:
    L = sum_i w_i * (xg_home_i * log(lam_home_i) - lam_home_i
                     + xg_away_i * log(lam_away_i) - lam_away_i)

sum(alpha) = 0 is enforced for identifiability via reparameterization
(same trick as Dixon-Coles in this codebase).

O/U 2.5 probabilities assume independence of home and away totals:
    lam_total = lam_home + lam_away
    P(X+Y <= 2) = exp(-lam_total) * (1 + lam_total + lam_total^2 / 2)

All datetimes are NAIVE Python datetime objects (matches DuckDB TIMESTAMP).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import polars as pl
from scipy.optimize import minimize

MIN_XG_TRAIN_MATCHES = 200

_REQUIRED_COLS = (
    "home_team_id",
    "away_team_id",
    "home_xg",
    "away_xg",
    "kickoff_utc",
)


class InsufficientTrainingData(Exception):
    """Raised when fewer than min_train_matches xG rows are available."""


@dataclass(frozen=True)
class XGSkellamFit:
    """Fitted xG-Skellam parameters and metadata.

    Attributes:
        team_attack: alpha_i per team_id; sum constrained to 0.
        team_defense: beta_i per team_id.
        gamma_home_adv: log-additive home advantage scalar.
        xi_decay: time-decay rate (per day); 0.0 = uniform weights.
        log_likelihood: total log-likelihood at the optimum.
        n_train_matches: number of matches with non-NULL xG retained.
        as_of: PIT cutoff (naive UTC).
        optimizer_status: scipy.optimize.OptimizeResult.message.
        fit_seconds: wall time of the fit.
    """

    team_attack: dict[str, float]
    team_defense: dict[str, float]
    gamma_home_adv: float
    xi_decay: float
    log_likelihood: float
    n_train_matches: int
    as_of: datetime
    optimizer_status: str
    fit_seconds: float


def _filter_matches(matches: pl.DataFrame, as_of: datetime) -> pl.DataFrame:
    """Apply PIT filter and require non-NULL xG values.

    Args:
        matches: input frame; must contain all _REQUIRED_COLS.
        as_of: PIT cutoff; rows with kickoff_utc >= as_of are dropped.

    Returns:
        Filtered DataFrame.

    Raises:
        ValueError: if required columns are missing.
    """
    missing = set(_REQUIRED_COLS) - set(matches.columns)
    if missing:
        raise ValueError(f"matches missing required columns: {sorted(missing)}")
    return matches.filter(
        (pl.col("kickoff_utc") < as_of)
        & pl.col("home_xg").is_not_null()
        & pl.col("away_xg").is_not_null()
    )


def fit(
    matches: pl.DataFrame,
    *,
    as_of: datetime,
    xi_decay: float = 0.0019,
    rng_seed: int = 0,
    min_train_matches: int = MIN_XG_TRAIN_MATCHES,
) -> XGSkellamFit:
    """Fit xG-Skellam by Poisson kernel MLE with L-BFGS-B.

    Parameter vector layout for scipy (mirrors Dixon-Coles):
        [alpha_1, ..., alpha_{N-1}, beta_1, ..., beta_N, gamma]
    where alpha_N = -sum(alpha_1..N-1) for the zero-mean attack constraint.

    Args:
        matches: training matches with home_xg, away_xg, kickoff_utc.
        as_of: PIT cutoff (naive UTC).
        xi_decay: time-decay rate per day; reference is `as_of` (not
            max(kickoff_utc)) to avoid backtest leakage.
        rng_seed: seed for parameter initialization perturbation.
        min_train_matches: minimum xG-complete rows required; raises
            InsufficientTrainingData if the filtered set is smaller.

    Returns:
        XGSkellamFit with optimized parameters.

    Raises:
        InsufficientTrainingData: if fewer than min_train_matches rows
            survive the xG-complete + PIT filter.
        ValueError: if required columns are missing.
    """
    df = _filter_matches(matches, as_of)
    if df.height < min_train_matches:
        raise InsufficientTrainingData(
            f"only {df.height} xG-complete matches before {as_of} (need >= {min_train_matches})"
        )

    teams = sorted(set(df["home_team_id"].to_list()) | set(df["away_team_id"].to_list()))
    n = len(teams)
    if n < 2:
        raise InsufficientTrainingData(f"need >= 2 distinct teams, got {n}")

    team_idx = {t: i for i, t in enumerate(teams)}
    home_idx = np.array([team_idx[h] for h in df["home_team_id"].to_list()], dtype=int)
    away_idx = np.array([team_idx[a] for a in df["away_team_id"].to_list()], dtype=int)
    xg_home = np.array(df["home_xg"].to_list(), dtype=float)
    xg_away = np.array(df["away_xg"].to_list(), dtype=float)
    kickoffs = df["kickoff_utc"].to_list()

    if xi_decay > 0.0:
        deltas = np.array([(as_of - t).total_seconds() / 86400.0 for t in kickoffs])
        weights = np.exp(-xi_decay * deltas)
    else:
        weights = np.ones(len(home_idx))

    rng = np.random.default_rng(rng_seed)
    x0_alpha = rng.normal(0.0, 0.05, size=n - 1)
    x0_beta = rng.normal(0.0, 0.05, size=n)
    x0 = np.concatenate([x0_alpha, x0_beta, [0.30]])  # gamma ~ 0.30

    def unpack(params: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        alpha_short = params[: n - 1]
        alpha_full = np.concatenate([alpha_short, [-alpha_short.sum()]])
        beta = params[n - 1 : 2 * n - 1]
        gamma = float(params[2 * n - 1])
        return alpha_full, beta, gamma

    def neg_ll(params: np.ndarray) -> float:
        alpha, beta, gamma = unpack(params)
        log_lam_home = alpha[home_idx] - beta[away_idx] + gamma
        log_lam_away = alpha[away_idx] - beta[home_idx]
        lam_home = np.exp(log_lam_home)
        lam_away = np.exp(log_lam_away)
        per_match = xg_home * log_lam_home - lam_home + xg_away * log_lam_away - lam_away
        return float(-np.sum(weights * per_match))

    bounds = (
        [(-3.0, 3.0)] * (n - 1)  # alpha_short
        + [(-3.0, 3.0)] * n  # beta
        + [(-1.0, 2.0)]  # gamma
    )

    t0 = time.perf_counter()
    result = minimize(neg_ll, x0, method="L-BFGS-B", bounds=bounds)
    fit_seconds = time.perf_counter() - t0

    alpha_full, beta_full, gamma_opt = unpack(result.x)
    return XGSkellamFit(
        team_attack={teams[i]: float(alpha_full[i]) for i in range(n)},
        team_defense={teams[i]: float(beta_full[i]) for i in range(n)},
        gamma_home_adv=float(gamma_opt),
        xi_decay=float(xi_decay),
        log_likelihood=float(-result.fun),
        n_train_matches=int(df.height),
        as_of=as_of,
        optimizer_status=str(result.message),
        fit_seconds=float(fit_seconds),
    )


def predict_ou25(
    fitted: XGSkellamFit,
    home_team_id: str,
    away_team_id: str,
) -> tuple[float, float]:
    """Predict O/U 2.5 probabilities under the xG-Skellam model.

    Assumes total goals X+Y ~ Poisson(lam_home + lam_away) (independence).
    P(X+Y <= 2) uses the Poisson CDF closed form for k=0,1,2.

    Args:
        fitted: parameters from `fit()`.
        home_team_id: must exist in fitted.team_attack.
        away_team_id: must exist in fitted.team_attack.

    Returns:
        (p_over, p_under) summing to 1.0.

    Raises:
        KeyError: if either team_id is unknown to the fit.
    """
    if home_team_id not in fitted.team_attack:
        raise KeyError(f"unknown home_team_id: {home_team_id}")
    if away_team_id not in fitted.team_attack:
        raise KeyError(f"unknown away_team_id: {away_team_id}")

    log_lam_home = (
        fitted.team_attack[home_team_id] - fitted.team_defense[away_team_id] + fitted.gamma_home_adv
    )
    log_lam_away = fitted.team_attack[away_team_id] - fitted.team_defense[home_team_id]
    lam_total = float(np.exp(log_lam_home) + np.exp(log_lam_away))
    p_under = float(np.exp(-lam_total) * (1.0 + lam_total + lam_total**2 / 2.0))
    p_under = max(0.0, min(1.0, p_under))
    return (1.0 - p_under, p_under)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    base = datetime(2020, 1, 1)
    rows = [
        {
            "home_team_id": "a" if i % 2 == 0 else "b",
            "away_team_id": "b" if i % 2 == 0 else "a",
            "home_xg": float(rng.exponential(1.4)),
            "away_xg": float(rng.exponential(1.0)),
            "kickoff_utc": datetime(2020, 1, 1 + i),
        }
        for i in range(220)
    ]
    df = pl.DataFrame(rows)
    xg = fit(df, as_of=datetime(2022, 1, 1))
    p_over, p_under = predict_ou25(xg, "a", "b")
    print(
        f"xG-Skellam smoke: p_over={p_over:.3f} p_under={p_under:.3f} "
        f"ll={xg.log_likelihood:.2f} n={xg.n_train_matches}"
    )
