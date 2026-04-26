"""Per-column Phase B audit report for migration 002.

Runs a dry simulation of Phase B against the warehouse DB and reports for each
of the 52 promoted source keys:
  - extras_present: rows where extras has the source key
  - extras_castable: rows where extras has the source key AND TRY_CAST AS DOUBLE returns non-NULL
  - extras_uncastable: extras_present - extras_castable (the gap that fails the audit)

Use this BEFORE applying migration 002 to see which columns will pass / fail
the gate. Migration 002's gate halts when typed_count < extras_count; on the
initial run typed is NULL so typed_count == extras_castable, meaning any
extras_uncastable > 0 will fail the audit.

This script is read-only — does not modify the DB.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

DB_PATH = Path("data/warehouse/footy_ev.duckdb")

PROMOTED_SOURCE_NAMES: tuple[str, ...] = (
    "B365CH",
    "B365CD",
    "B365CA",
    "BWCH",
    "BWCD",
    "BWCA",
    "WHCH",
    "WHCD",
    "WHCA",
    "PSCH",
    "PSCD",
    "PSCA",
    "IWCH",
    "IWCD",
    "IWCA",
    "VCCH",
    "VCCD",
    "VCCA",
    "MaxCH",
    "MaxCD",
    "MaxCA",
    "AvgCH",
    "AvgCD",
    "AvgCA",
    "BFECH",
    "BFECD",
    "BFECA",
    "B365C>2.5",
    "B365C<2.5",
    "MaxC>2.5",
    "MaxC<2.5",
    "AvgC>2.5",
    "AvgC<2.5",
    "PC>2.5",
    "PC<2.5",
    "BFEC>2.5",
    "BFEC<2.5",
    "AHCh",
    "B365CAHH",
    "B365CAHA",
    "MaxCAHH",
    "MaxCAHA",
    "AvgCAHH",
    "AvgCAHA",
    "PCAHH",
    "PCAHA",
    "BFECAHH",
    "BFECAHA",
    "MaxAHH",
    "MaxAHA",
    "AvgAHH",
    "AvgAHA",
)


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows: list[tuple[str, int, int, int]] = []
        for src in PROMOTED_SOURCE_NAMES:
            present = con.execute(
                "SELECT COUNT(*) FROM raw_match_results "
                "WHERE list_contains(map_keys(extras), ?)",
                [src],
            ).fetchone()[0]
            castable = con.execute(
                "SELECT COUNT(*) FROM raw_match_results "
                "WHERE TRY_CAST(extras[?] AS DOUBLE) IS NOT NULL",
                [src],
            ).fetchone()[0]
            uncastable = present - castable
            rows.append((src, present, castable, uncastable))

        print(f"{'source_key':<14} {'present':>8} {'castable':>9} {'uncastable':>11}  status")
        print("-" * 60)
        n_fail = 0
        for src, present, castable, uncastable in rows:
            status = "FAIL" if uncastable > 0 else "ok"
            if uncastable > 0:
                n_fail += 1
            print(f"{src:<14} {present:>8d} {castable:>9d} {uncastable:>11d}  {status}")

        print()
        if n_fail == 0:
            print("All 52 columns pass the audit gate.")
        else:
            print(f"{n_fail} columns will FAIL the Phase B audit gate.")
            print("Investigate the uncastable values before re-running migration 002:")
            print()
            for src, _, _, uncastable in rows:
                if uncastable == 0:
                    continue
                # Show 5 sample uncastable values per failing column.
                samples = con.execute(
                    "SELECT extras[?] FROM raw_match_results "
                    "WHERE list_contains(map_keys(extras), ?) "
                    "AND TRY_CAST(extras[?] AS DOUBLE) IS NULL "
                    "LIMIT 5",
                    [src, src, src],
                ).fetchall()
                vals = [repr(s[0]) for s in samples]
                print(f"  {src} ({uncastable} uncastable): sample values = {vals}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
