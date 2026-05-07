"""Integration test: hits the real Understat AJAX endpoint.

Gated on ``FOOTY_EV_INTEGRATION_NETWORK=1`` per CLAUDE.md politeness rules.
Mirrors the football-data integration test pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.ingestion.understat.loader import load_season
from footy_ev.ingestion.understat.source import fetch_season


@pytest.mark.skipif(
    os.environ.get("FOOTY_EV_INTEGRATION_NETWORK") != "1",
    reason="requires FOOTY_EV_INTEGRATION_NETWORK=1 (hits the real network)",
)
def test_understat_fetch_and_load_real_season(tmp_path: Path) -> None:
    """Fetch one current season via the live AJAX endpoint and load it.

    Asserts at least 50 matches parsed and loaded — the same R4 floor used by
    the parse-layer to detect endpoint shape changes. A pass here means the
    AJAX endpoint, header requirements, parser, and loader all agree end-to-end.
    """
    raw_dir = tmp_path / "raw"
    db_path = tmp_path / "wh.duckdb"

    json_path = fetch_season("EPL", "2024-2025", raw_dir=raw_dir)
    assert json_path.exists()
    assert json_path.stat().st_size > 100_000  # season payload is ~900KB

    con = duckdb.connect(str(db_path))
    try:
        apply_migrations(con)
        apply_views(con)
        report = load_season(league="EPL", season="2024-2025", json_path=json_path, con=con)
    finally:
        con.close()

    assert report.inserted >= 50
    assert report.rejected == 0
    assert report.total() == report.inserted + report.updated + report.unchanged + report.rejected
