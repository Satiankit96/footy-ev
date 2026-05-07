"""One-shot diagnostic: per-season coverage of PSCH and B365CH after migration 002.

Run: ``uv run python notebooks/001_closing_odds_coverage.py``

Confirms migration 002's extraction matches expected bookmaker coverage start
dates before Phase 0 step 2 (Understat) builds on this layer. Read-only — does
not write to the warehouse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path("data/warehouse/footy_ev.duckdb")
PLOT_PATH = Path("reports/closing_odds_coverage.png")

QUERY = """
WITH per_season AS (
    SELECT
        season,
        COUNT(*)                                    AS total_rows,
        SUM(CASE WHEN psch   IS NOT NULL THEN 1 ELSE 0 END) AS psch_non_null,
        SUM(CASE WHEN b365ch IS NOT NULL THEN 1 ELSE 0 END) AS b365ch_non_null
    FROM raw_match_results
    GROUP BY season
)
SELECT
    season,
    total_rows,
    psch_non_null,
    ROUND(100.0 * psch_non_null   / total_rows, 1) AS psch_pct,
    b365ch_non_null,
    ROUND(100.0 * b365ch_non_null / total_rows, 1) AS b365ch_pct
FROM per_season
ORDER BY season ASC;
"""


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(QUERY).pl()
    finally:
        con.close()

    with pl.Config(tbl_rows=-1, tbl_width_chars=120):
        print(df)

    psch_starts = df.filter(pl.col("psch_pct") > 50).select("season").to_series().to_list()
    b365_starts = df.filter(pl.col("b365ch_pct") > 50).select("season").to_series().to_list()

    psch_start = psch_starts[0] if psch_starts else None
    b365_start = b365_starts[0] if b365_starts else None

    psch_gaps: list[tuple[str, float]] = []
    b365_gaps: list[tuple[str, float]] = []
    if psch_start is not None:
        psch_gaps = [
            (s, p)
            for s, p in df.filter(pl.col("season") >= psch_start)
            .select(["season", "psch_pct"])
            .iter_rows()
            if p < 95.0
        ]
    if b365_start is not None:
        b365_gaps = [
            (s, p)
            for s, p in df.filter(pl.col("season") >= b365_start)
            .select(["season", "b365ch_pct"])
            .iter_rows()
            if p < 95.0
        ]

    print()
    print(f"PSCH coverage starts in season: {psch_start or '<never crosses 50%>'}")
    print(f"B365CH coverage starts in season: {b365_start or '<never crosses 50%>'}")

    gaps_combined: list[str] = []
    for s, p in psch_gaps:
        gaps_combined.append(f"PSCH@{s}={p}%")
    for s, p in b365_gaps:
        gaps_combined.append(f"B365CH@{s}={p}%")
    print(
        "Any season post-coverage-start with pct < 95%: "
        + (", ".join(gaps_combined) if gaps_combined else "none")
    )

    PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print()
        print(f"[plot skipped] matplotlib not installed; {PLOT_PATH} not written.")
        return

    seasons = df.get_column("season").to_list()
    psch_pct = df.get_column("psch_pct").to_list()
    b365ch_pct = df.get_column("b365ch_pct").to_list()

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(seasons, psch_pct, marker="o", label="PSCH (Pinnacle close)")
    ax.plot(seasons, b365ch_pct, marker="s", label="B365CH (Bet365 close)")
    ax.set_ylabel("Coverage %")
    ax.set_xlabel("Season")
    ax.set_title("Closing-odds coverage per season — post migration 002")
    ax.set_ylim(0, 105)
    ax.axhline(95, linestyle="--", linewidth=0.8, alpha=0.5)
    ax.legend()
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=120)
    plt.close(fig)
    print()
    print(f"[plot] wrote {PLOT_PATH}")


if __name__ == "__main__":
    main()
