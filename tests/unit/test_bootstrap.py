"""Unit tests for bootstrap_edge_ci.

Tests:
    1. Coverage test: 95% CI contains the true mean in >=90/100 simulations.
    2. Empty winners: returns n_winners=0 and nan CI values.
    3. All-positive distribution: p_value_above_zero is effectively zero.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pytest

from footy_ev.eval.bootstrap import bootstrap_edge_ci


def _make_bootstrap_db(
    run_id: str,
    edges: list[float],
    is_winner_flags: list[bool],
) -> duckdb.DuckDBPyConnection:
    """Minimal in-memory DB with only the columns bootstrap_edge_ci reads."""
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE clv_evaluations (
            evaluation_id VARCHAR PRIMARY KEY,
            run_id VARCHAR NOT NULL,
            prediction_id VARCHAR NOT NULL,
            fixture_id VARCHAR NOT NULL,
            market VARCHAR,
            selection VARCHAR NOT NULL,
            p_raw DOUBLE NOT NULL,
            p_calibrated DOUBLE NOT NULL,
            pinnacle_close_decimal DOUBLE NOT NULL,
            pinnacle_q_devigged DOUBLE NOT NULL,
            devig_method VARCHAR NOT NULL,
            edge_at_close DOUBLE NOT NULL,
            is_winner BOOLEAN NOT NULL,
            would_have_bet BOOLEAN NOT NULL,
            evaluated_at TIMESTAMP NOT NULL
        )
    """)
    for i, (edge, is_win) in enumerate(zip(edges, is_winner_flags, strict=False)):
        con.execute(
            """
            INSERT INTO clv_evaluations VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
            """,
            [
                f"ev{i}",
                run_id,
                f"pred{i}",
                f"fix{i}",
                "1x2",
                "home",
                0.5,
                0.5,
                2.0,
                0.5,
                "shin",
                edge,
                is_win,
                edge > 0.03,
            ],
        )
    return con


def test_bootstrap_ci_coverage() -> None:
    """95% percentile CI must contain the true mean in >=90 of 100 simulations."""
    true_mean = 0.05
    n_samples = 200
    n_simulations = 100
    rng = np.random.default_rng(42)

    contained = 0
    for sim_idx in range(n_simulations):
        edges = rng.normal(true_mean, 0.1, n_samples).tolist()
        is_winner = [True] * n_samples
        con = _make_bootstrap_db(f"run_{sim_idx}", edges, is_winner)
        result = bootstrap_edge_ci(con, f"run_{sim_idx}", n_resamples=2000, rng_seed=sim_idx)
        if result["ci_low"] <= true_mean <= result["ci_high"]:
            contained += 1

    assert contained >= 90, (
        f"95% CI contained true mean in {contained}/100 simulations (expected >= 90)"
    )


def test_bootstrap_empty_winners_returns_nan() -> None:
    """No is_winner=TRUE rows -> n_winners=0, CI values are nan."""
    con = _make_bootstrap_db("run_empty", [], [])
    result = bootstrap_edge_ci(con, "run_empty")

    assert result["n_winners"] == 0
    assert result["n_resamples"] == 10_000
    assert math.isnan(result["mean"])
    assert math.isnan(result["ci_low"])
    assert math.isnan(result["ci_high"])
    assert math.isnan(result["p_value_above_zero"])


def test_bootstrap_all_positive_p_value_near_zero() -> None:
    """All edges strongly positive -> p_value_above_zero == 0.0 and ci_low > 0."""
    edges = [0.10] * 300
    is_winner = [True] * 300
    con = _make_bootstrap_db("run_pos", edges, is_winner)
    result = bootstrap_edge_ci(con, "run_pos", n_resamples=5_000)

    assert result["p_value_above_zero"] == pytest.approx(0.0, abs=1e-9)
    assert result["ci_low"] > 0
    assert result["ci_high"] > 0
    assert result["n_winners"] == 300
