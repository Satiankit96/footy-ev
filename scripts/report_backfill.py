"""Generate the post-backfill report for review."""

from __future__ import annotations

from pathlib import Path

import duckdb

DB_PATH = Path("data/warehouse/footy_ev.duckdb")
RAW_DIR = Path("data/raw/football_data/E0")


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    print("=" * 70)
    print("Per-season row counts (oldest first)")
    print("=" * 70)
    rows = con.execute(
        "SELECT season, COUNT(*) FROM raw_match_results "
        "WHERE league = 'EPL' GROUP BY season ORDER BY season"
    ).fetchall()
    total = 0
    for season, count in rows:
        print(f"  {season}: {count}")
        total += count
    print(f"  TOTAL: {total}")

    print()
    print("=" * 70)
    print("Per-season <HEADER_OVERFLOW> field-count sets")
    print("=" * 70)
    overflow_rows = con.execute(
        "SELECT season, sample_values "
        "FROM schema_drift_log "
        "WHERE league = 'EPL' AND column_name = '<HEADER_OVERFLOW>' "
        "ORDER BY season"
    ).fetchall()
    if not overflow_rows:
        print("  (none — every season's CSV header matched its row widths)")
    else:
        for season, sample_values in overflow_rows:
            widths = sorted(int(s) for s in sample_values)
            print(f"  {season}: {widths}")

    print()
    print("=" * 70)
    print("CSV-vs-DB sanity: row count comparison")
    print("=" * 70)
    season_codes = {f"{y}-{y + 1}": f"{str(y)[-2:]}{str(y + 1)[-2:]}" for y in range(2000, 2026)}
    db_per_season = dict(rows)
    for season, code in season_codes.items():
        csv_path = RAW_DIR / f"{code}.csv"
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8", errors="replace") as f:
            csv_rows = sum(1 for _ in f) - 1  # exclude header
        db_count = db_per_season.get(season, 0)
        flag = "" if csv_rows == db_count else f"  <-- delta {csv_rows - db_count}"
        print(f"  {season}: csv={csv_rows}, db={db_count}{flag}")

    print()
    print("=" * 70)
    print("Unknown columns: first-seen season (registry promotion candidates)")
    print("=" * 70)
    unknown = con.execute(
        """
        SELECT column_name, MIN(season) AS first_seen,
               COUNT(DISTINCT season) AS seen_in_seasons
        FROM schema_drift_log
        WHERE league = 'EPL'
          AND column_name <> '<HEADER_OVERFLOW>'
          AND column_name NOT LIKE '\\_overflow\\_pos\\_%' ESCAPE '\\'
        GROUP BY column_name
        ORDER BY first_seen, column_name
        """
    ).fetchall()
    print(f"  {len(unknown)} distinct unknown columns observed")
    for col, first_seen, span in unknown:
        print(f"    {first_seen}  {col!r:<28}  (in {span} season(s))")

    print()
    print("=" * 70)
    print("Overflow positions: first-seen season")
    print("=" * 70)
    overflow_positions = con.execute(
        r"""
        SELECT column_name, MIN(season) AS first_seen,
               COUNT(DISTINCT season) AS seen_in_seasons
        FROM schema_drift_log
        WHERE league = 'EPL'
          AND column_name LIKE '\_overflow\_pos\_%' ESCAPE '\'
        GROUP BY column_name
        ORDER BY first_seen, CAST(SUBSTRING(column_name, 15) AS INTEGER)
        """
    ).fetchall()
    if not overflow_positions:
        print("  (none — but expected to appear if any season's rows were ragged)")
    else:
        print(f"  {len(overflow_positions)} distinct overflow positions observed")
        for col, first_seen, span in overflow_positions:
            print(f"    {first_seen}  {col:<25}  (in {span} season(s))")

    con.close()


if __name__ == "__main__":
    main()
