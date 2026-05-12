"""CLV backfill: populate paper_bets.closing_odds and clv_pct after kickoff.

Closing-odds source hierarchy (BLUE_MAP §5):
  1. Kalshi live close  — last live_odds_snapshots row for venue='kalshi'
                          with received_at closest to kickoff.
  2. Pinnacle historical — v_pinnacle_close_epl (static CSV data, backtest only).
  3. NULL               — logged as a miss; clv_pct left NULL.

CLV formula:
    clv_pct = (odds_at_decision / closing_odds) - 1

Positive CLV → we captured better odds than the closing line.
Negative CLV → we paid worse than close.

Run this after settlement (or schedule it to run daily) to keep the
paper_bets table's clv_pct column current.
"""

from __future__ import annotations

import logging
from typing import Any

import duckdb

_LOG = logging.getLogger(__name__)


def backfill_clv(
    con: duckdb.DuckDBPyConnection,
    *,
    venue: str = "kalshi",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill closing_odds and clv_pct for settled paper_bets.

    Only rows with `settlement_status='settled'` and NULL `closing_odds`
    are processed. Rows without a closing price source remain NULL.

    Args:
        con: open DuckDB connection (read+write).
        venue: primary venue to look up in live_odds_snapshots ("kalshi").
               Pinnacle is always tried as fallback.
        dry_run: if True, print what would be updated without writing.

    Returns:
        Dict with keys: n_updated, n_kalshi_close, n_pinnacle_close, n_miss.
    """
    pending = con.execute(
        """
        SELECT decision_id, fixture_id, market, selection, odds_at_decision
        FROM paper_bets
        WHERE settlement_status = 'settled'
          AND closing_odds IS NULL
        """,
    ).fetchall()

    if not pending:
        _LOG.info("clv_backfill: no settled bets with missing closing_odds")
        return {"n_updated": 0, "n_kalshi_close": 0, "n_pinnacle_close": 0, "n_miss": 0}

    n_venue = 0
    n_pinnacle = 0
    n_miss = 0

    for decision_id, fixture_id, market, selection, odds_at_decision in pending:
        closing = _kalshi_close(con, fixture_id, market, selection, venue)
        source = venue if closing is not None else None

        if closing is None:
            closing = _pinnacle_close(con, fixture_id, market, selection)
            source = "pinnacle" if closing is not None else None

        if closing is None:
            n_miss += 1
            _LOG.info(
                "clv_backfill: miss — no closing odds for decision_id=%s "
                "fixture=%s market=%s selection=%s",
                decision_id,
                fixture_id,
                market,
                selection,
            )
            continue

        clv_pct = float(odds_at_decision) / float(closing) - 1.0
        if source in (venue,):
            n_venue += 1
        else:
            n_pinnacle += 1

        if dry_run:
            _LOG.info(
                "clv_backfill [DRY RUN]: %s closing=%s clv=%.3f%% source=%s",
                decision_id,
                closing,
                clv_pct * 100,
                source,
            )
            continue

        con.execute(
            """
            UPDATE paper_bets
            SET closing_odds = ?,
                clv_pct      = ?
            WHERE decision_id = ?
            """,
            [closing, clv_pct, decision_id],
        )

    n_updated = n_venue + n_pinnacle
    _LOG.info(
        "clv_backfill: updated=%d (%s=%d, pinnacle=%d, miss=%d)",
        n_updated,
        venue,
        n_venue,
        n_pinnacle,
        n_miss,
    )
    return {
        "n_updated": n_updated,
        f"n_{venue}_close": n_venue,
        "n_pinnacle_close": n_pinnacle,
        "n_miss": n_miss,
    }


def _kalshi_close(
    con: duckdb.DuckDBPyConnection,
    fixture_id: str,
    market: str,
    selection: str,
    venue: str,
) -> float | None:
    """Return the last live_odds_snapshots entry for (venue, fixture, market, selection).

    This represents the Kalshi closing price for paper bets — the final market
    quote before kickoff that was observed by the scraper.

    Returns None if no snapshot exists for this combination.
    """
    row = con.execute(
        """
        SELECT odds_decimal
        FROM live_odds_snapshots
        WHERE venue      = ?
          AND fixture_id = ?
          AND market     = ?
          AND selection  = ?
        ORDER BY received_at DESC
        LIMIT 1
        """,
        [venue, fixture_id, market, selection],
    ).fetchone()
    return float(row[0]) if row is not None else None


def _pinnacle_close(
    con: duckdb.DuckDBPyConnection,
    fixture_id: str,
    market: str,
    selection: str,
) -> float | None:
    """Return the Pinnacle historical closing price from v_pinnacle_close_epl.

    Only available for historical fixtures where the football-data CSV has
    Pinnacle columns (psch/pscd/psca/pc_over_25/pc_under_25).

    Returns None if the fixture or market/selection is not in the view.
    """
    try:
        row = con.execute(
            """
            SELECT pinnacle_close_decimal
            FROM v_pinnacle_close_epl
            WHERE fixture_id = ?
              AND market     = ?
              AND selection  = ?
            """,
            [fixture_id, market, selection],
        ).fetchone()
    except Exception:  # noqa: BLE001 — view may not exist in all test environments
        return None
    return float(row[0]) if row is not None and row[0] is not None else None


if __name__ == "__main__":
    import duckdb as _duckdb

    from footy_ev.db import apply_migrations, apply_views

    _con = _duckdb.connect(":memory:")
    apply_migrations(_con)
    apply_views(_con)
    result = backfill_clv(_con, dry_run=True)
    print(f"smoke: backfill_clv (empty DB) → {result}")
