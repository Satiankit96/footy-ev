"""Bootstrap confidence interval on mean edge for realized winners.

The resample is restricted to clv_evaluations WHERE is_winner = TRUE,
matching the canonical thesis-test metric (mean_edge_winners).

p_value_above_zero is the fraction of bootstrap resample means that are
<= 0 — the one-sided p-value for H0: mu <= 0 (the model has no edge on
realized winners). A small value (e.g. < 0.05) means few resamples
returned a non-positive mean, providing evidence against the null.

CI method: percentile bootstrap. Boundaries are
np.quantile(resample_means, [alpha/2, 1 - alpha/2]). BCa and studentized
variants are intentionally not used — percentile is sufficient for the
go/no-go verdict logic and matches what operators can verify manually.
"""

from __future__ import annotations

from typing import Any

import duckdb
import numpy as np


def bootstrap_edge_ci(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    *,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    rng_seed: int = 0,
) -> dict[str, Any]:
    """Bootstrap percentile CI on mean edge at close for realized winners.

    Args:
        con: open DuckDB connection (clv_evaluations must be populated).
        run_id: backtest run identifier.
        n_resamples: number of bootstrap draws with replacement.
        alpha: two-tailed significance level (default 0.05 -> 95% CI).
        rng_seed: seed for numpy.random.default_rng; ensures reproducibility.

    Returns:
        Dict with keys:
            mean: observed mean edge on winners (float, nan if n_winners=0).
            ci_low: lower bound of (1-alpha) CI (nan if n_winners=0).
            ci_high: upper bound of (1-alpha) CI (nan if n_winners=0).
            p_value_above_zero: fraction of resample means <= 0, i.e. the
                one-sided p-value for H0: mu <= 0.  Small values indicate
                the observed positive mean is unlikely under the null.
                (nan if n_winners=0).
            n_winners: count of is_winner=TRUE rows used.
            n_resamples: n_resamples as requested.
    """
    rows = con.execute(
        "SELECT edge_at_close FROM clv_evaluations WHERE run_id = ? AND is_winner = TRUE",
        [run_id],
    ).fetchall()

    n_winners = len(rows)
    nan = float("nan")
    if n_winners == 0:
        return {
            "mean": nan,
            "ci_low": nan,
            "ci_high": nan,
            "p_value_above_zero": nan,
            "n_winners": 0,
            "n_resamples": n_resamples,
        }

    edges = np.array([r[0] for r in rows], dtype=float)
    observed_mean = float(edges.mean())

    rng = np.random.default_rng(rng_seed)
    resample_means = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        sample = rng.choice(edges, size=n_winners, replace=True)
        resample_means[i] = sample.mean()

    ci_low, ci_high = np.quantile(resample_means, [alpha / 2, 1.0 - alpha / 2])
    p_value = float(np.mean(resample_means <= 0))

    return {
        "mean": observed_mean,
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "p_value_above_zero": p_value,
        "n_winners": n_winners,
        "n_resamples": n_resamples,
    }


if __name__ == "__main__":
    import duckdb as _duckdb

    _con = _duckdb.connect(":memory:")
    _con.execute("""
        CREATE TABLE clv_evaluations (
            evaluation_id VARCHAR, run_id VARCHAR, prediction_id VARCHAR,
            fixture_id VARCHAR, market VARCHAR, selection VARCHAR,
            p_raw DOUBLE, p_calibrated DOUBLE, pinnacle_close_decimal DOUBLE,
            pinnacle_q_devigged DOUBLE, devig_method VARCHAR,
            edge_at_close DOUBLE, is_winner BOOLEAN,
            would_have_bet BOOLEAN, evaluated_at TIMESTAMP
        )
    """)
    rng_ = np.random.default_rng(0)
    for i in range(500):
        edge = float(rng_.normal(0.02, 0.08))
        _con.execute(
            "INSERT INTO clv_evaluations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NOW())",
            [
                f"e{i}",
                "smoke",
                f"p{i}",
                f"f{i}",
                "1x2",
                "home",
                0.5,
                0.5,
                2.0,
                0.5,
                "shin",
                edge,
                True,
                edge > 0.03,
            ],
        )
    result = bootstrap_edge_ci(_con, "smoke")
    print(
        f"n={result['n_winners']} mean={result['mean']:+.4f} "
        f"CI=[{result['ci_low']:+.4f}, {result['ci_high']:+.4f}] "
        f"p={result['p_value_above_zero']:.3f}"
    )
