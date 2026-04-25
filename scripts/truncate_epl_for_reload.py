"""One-shot helper to clear EPL data before the post-fix backfill rerun.

Usage:
    uv run python scripts/truncate_epl_for_reload.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb

DB_PATH = Path("data/warehouse/footy_ev.duckdb")


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    try:
        before_counts = con.execute(
            "SELECT season, COUNT(*) FROM raw_match_results "
            "WHERE league = 'EPL' GROUP BY season ORDER BY season"
        ).fetchall()
        before_drift = con.execute(
            "SELECT COUNT(*) FROM schema_drift_log WHERE league = 'EPL'"
        ).fetchone()[0]

        print("Before truncate:")
        for season, count in before_counts:
            print(f"  {season}: {count}")
        print(f"  schema_drift_log (EPL): {before_drift}")

        con.execute("DELETE FROM raw_match_results WHERE league = 'EPL'")
        con.execute("DELETE FROM schema_drift_log WHERE league = 'EPL'")

        after_rows = con.execute(
            "SELECT COUNT(*) FROM raw_match_results WHERE league = 'EPL'"
        ).fetchone()[0]
        after_drift = con.execute(
            "SELECT COUNT(*) FROM schema_drift_log WHERE league = 'EPL'"
        ).fetchone()[0]

        print("\nAfter truncate:")
        print(f"  raw_match_results (EPL): {after_rows}")
        print(f"  schema_drift_log (EPL): {after_drift}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
