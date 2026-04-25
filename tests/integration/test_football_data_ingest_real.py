r"""Real-network integration test for football-data.co.uk ingestion.

Hits football-data.co.uk for 2024-2025 EPL (E0.csv). Gated on
``FOOTY_EV_INTEGRATION_NETWORK=1`` so CI or default local runs do NOT accidentally
fetch from the upstream host.

Run with:
    set FOOTY_EV_INTEGRATION_NETWORK=1  (Windows cmd)
    $env:FOOTY_EV_INTEGRATION_NETWORK = "1"  (PowerShell)
    export FOOTY_EV_INTEGRATION_NETWORK=1  (bash)

then: ``.\make.ps1 test-integration`` or ``uv run pytest tests/integration -v``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import duckdb
import pytest

if TYPE_CHECKING:
    from pathlib import Path

from footy_ev.db import apply_migrations
from footy_ev.ingestion.football_data.loader import load_season
from footy_ev.ingestion.football_data.source import fetch_season

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("FOOTY_EV_INTEGRATION_NETWORK") != "1",
        reason="requires FOOTY_EV_INTEGRATION_NETWORK=1 (hits the real network)",
    ),
]


def test_fetch_and_load_real_2024_2025_epl(tmp_path: Path) -> None:
    """Single-season end-to-end: fetch, load, idempotent re-run."""
    raw_dir = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    csv = fetch_season("EPL", "2024-2025", raw_dir=raw_dir)
    assert csv.exists(), "fetch_season should produce a cached CSV"
    assert csv.stat().st_size > 10_000, "EPL CSV should be non-trivial in size"

    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    try:
        first = load_season(league="EPL", season="2024-2025", csv_path=csv, con=con)
        assert (
            first.rejected == 0
        ), f"expected zero rejected rows on real EPL data, got {first.rejected}"
        assert (
            first.inserted >= 300
        ), f"EPL season has 380 matches; expected >=300 inserted, got {first.inserted}"
        assert first.total() == first.inserted
        assert first.updated == 0
        assert first.unchanged == 0

        # Idempotency canary on real data
        second = load_season(league="EPL", season="2024-2025", csv_path=csv, con=con)
        assert second.inserted == 0
        assert second.updated == 0
        assert second.unchanged == first.inserted
        assert second.rejected == 0

        # DuckDB row count should match report
        count = int(con.execute("SELECT COUNT(*) FROM raw_match_results").fetchone()[0])
        assert count == first.inserted

        # Print a human-readable report for CI logs / operator review
        print("")
        print(f"[EPL 2024-2025] first:  {first}")
        print(f"[EPL 2024-2025] second: {second}")
        print(f"[EPL 2024-2025] row_count_in_db={count}")
        print(f"[EPL 2024-2025] unknown_columns={first.unknown_columns}")
    finally:
        con.close()
