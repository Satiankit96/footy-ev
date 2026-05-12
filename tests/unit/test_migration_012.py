"""Migration 012: 3-letter EPL team-code aliases in team_aliases.

Verifies all 20 codes seed correctly and that re-running is idempotent.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from footy_ev.db import apply_migrations

EXPECTED_CODES_TO_TEAM_IDS = {
    "ARS": "arsenal",
    "AVL": "aston_villa",
    "BHA": "brighton",
    "BOU": "bournemouth",
    "BRE": "brentford",
    "BUR": "burnley",
    "CHE": "chelsea",
    "CRY": "crystal_palace",
    "EVE": "everton",
    "FUL": "fulham",
    "LEE": "leeds",
    "LIV": "liverpool",
    "MCI": "man_city",
    "MUN": "man_united",
    "NEW": "newcastle",
    "NFO": "nottm_forest",
    "SUN": "sunderland",
    "TOT": "tottenham",
    "WHU": "west_ham",
    "WOL": "wolves",
}


def test_seeds_all_twenty_codes(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    apply_migrations(con)
    rows = con.execute(
        "SELECT raw_name, team_id FROM team_aliases WHERE source = 'kalshi_code'"
    ).fetchall()
    actual = {str(r[0]): str(r[1]) for r in rows}
    assert actual == EXPECTED_CODES_TO_TEAM_IDS


def test_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db_path))
    apply_migrations(con)
    n1 = con.execute("SELECT COUNT(*) FROM team_aliases WHERE source = 'kalshi_code'").fetchone()[0]
    # Re-apply: INSERT OR IGNORE on the (source, raw_name) PK should be a no-op.
    apply_migrations(con)
    n2 = con.execute("SELECT COUNT(*) FROM team_aliases WHERE source = 'kalshi_code'").fetchone()[0]
    assert n1 == n2 == 20
