"""Integration test: full walk-forward over real EPL warehouse.

Gated behind FOOTY_EV_INTEGRATION_DB=1 because it requires the populated
warehouse at data/warehouse/footy_ev.duckdb. Copies the warehouse to a
temp file before running so the source DB is never mutated.

Configured to exercise the harness over a small slice (warmup through end
of 2024-2025, backtest covers 2025-2026 only) so the test runs in
reasonable time on a laptop.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import duckdb
import pytest

from footy_ev.backtest.walkforward import run_backtest
from footy_ev.db import apply_migrations, apply_views

INTEGRATION = os.environ.get("FOOTY_EV_INTEGRATION_DB") == "1"
WAREHOUSE = Path("data/warehouse/footy_ev.duckdb")


@pytest.mark.skipif(
    not INTEGRATION,
    reason="requires FOOTY_EV_INTEGRATION_DB=1 (uses populated warehouse)",
)
@pytest.mark.skipif(
    not WAREHOUSE.exists(),
    reason=f"warehouse db not present at {WAREHOUSE}",
)
def test_run_backtest_epl_two_seasons(tmp_path):
    """Full walk-forward over 2025-2026 only: writes predictions, no PIT leakage."""
    dst = tmp_path / "footy_ev_test.duckdb"
    shutil.copy(WAREHOUSE, dst)

    con = duckdb.connect(str(dst))
    apply_migrations(con)
    apply_views(con)

    # 26 seasons available (2000-01..2025-26). train_min_seasons=25 means
    # warmup ends at end of season index 24 = 2024-2025; backtest covers
    # only 2025-2026 (~339 played matches as of latest ingest).
    run_id = run_backtest(
        con,
        "EPL",
        train_min_seasons=25,
        step_days=90,
        model_version="dc_v1",
    )

    # backtest_runs row reaches 'complete'
    row = con.execute(
        "SELECT status, n_folds, n_predictions FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    assert row[0] == "complete", f"status was {row[0]}"
    assert row[1] is not None and row[1] > 0, f"n_folds={row[1]}"
    assert row[2] is not None and row[2] >= 300, (
        f"n_predictions={row[2]}, expected >=300 (~100 matches × 3 selections)"
    )

    # PIT correctness: every prediction's as_of < its match's kickoff_utc.
    n_leaks = con.execute(
        """
        SELECT COUNT(*)
        FROM model_predictions p
        JOIN v_fixtures_epl f ON f.fixture_id = p.fixture_id
        WHERE p.run_id = ? AND p.as_of >= f.kickoff_utc
        """,
        [run_id],
    ).fetchone()[0]
    assert n_leaks == 0, f"PIT leakage: {n_leaks} predictions have as_of >= kickoff"

    # 1X2 sums-to-1 invariant across a sample of fixtures.
    sample = con.execute(
        """
        SELECT fixture_id, SUM(p_raw) AS total
        FROM model_predictions
        WHERE run_id = ? AND market = '1x2'
        GROUP BY fixture_id
        LIMIT 50
        """,
        [run_id],
    ).fetchall()
    assert len(sample) > 0
    for fid, total in sample:
        assert abs(total - 1.0) < 1e-6, f"fixture {fid} probs sum to {total}"

    # Three rows per fixture (home/draw/away), no duplicates within a run.
    bad_rows = con.execute(
        """
        SELECT fixture_id, COUNT(*) AS c
        FROM model_predictions
        WHERE run_id = ? AND market = '1x2'
        GROUP BY fixture_id
        HAVING COUNT(*) <> 3
        """,
        [run_id],
    ).fetchall()
    assert bad_rows == [], f"unexpected selection counts: {bad_rows[:5]}"

    # dc_fits / dc_team_params consistency: every fit_id present in
    # dc_fits has team rows in dc_team_params.
    orphan_fits = con.execute(
        """
        SELECT f.fit_id
        FROM dc_fits f
        LEFT JOIN dc_team_params p ON p.fit_id = f.fit_id
        WHERE f.model_version = 'dc_v1_test' AND p.fit_id IS NULL
        """,
    ).fetchall()
    assert orphan_fits == [], f"fits without team params: {orphan_fits}"
