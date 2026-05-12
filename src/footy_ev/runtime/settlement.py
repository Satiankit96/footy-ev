"""Venue-agnostic paper-bet settlement.

Settlement logic:
  1. Find paper_bets where settlement_status='pending'.
  2. Join to v_fixtures_epl to check if the fixture is 'final'.
  3. Determine win/loss for each market + selection:
     ou_2.5  over  → total_goals > 2
     ou_2.5  under → total_goals <= 2
  4. Compute pnl_gbp:
       winner → stake_gbp * (odds_at_decision - 1)
       loser  → -stake_gbp
  5. Write settlement results back to paper_bets.

Venue-agnostic: the same outcome logic applies to Kalshi YES/NO contracts
and Betfair Exchange bets because both map to the same internal market/selection
keys (ou_2.5 / over / under).

Run after each scraper tick or as a daily job.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import duckdb

_LOG = logging.getLogger(__name__)

# Supported markets and how to determine the winner from v_fixtures_epl columns.
# Each market maps selection → SQL expression returning a boolean.
_WIN_CONDITION: dict[str, dict[str, str]] = {
    "ou_2.5": {
        "over": "(home_score_ft + away_score_ft) > 2",
        "under": "(home_score_ft + away_score_ft) <= 2",
    },
    "1x2": {
        "home": "result_ft = 'H'",
        "draw": "result_ft = 'D'",
        "away": "result_ft = 'A'",
    },
}


def settle_pending_bets(
    con: duckdb.DuckDBPyConnection,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Settle all pending paper_bets whose fixture is now final.

    Args:
        con: open DuckDB connection (read+write).
        dry_run: if True, log what would be settled without writing.

    Returns:
        Dict with keys: n_settled, n_won, n_lost, n_skipped_no_result,
        n_skipped_unsupported_market, total_pnl_gbp.
    """
    rows = con.execute(
        """
        SELECT
            pb.decision_id,
            pb.fixture_id,
            pb.market,
            pb.selection,
            pb.stake_gbp,
            pb.odds_at_decision,
            f.status,
            f.home_score_ft,
            f.away_score_ft,
            f.result_ft
        FROM paper_bets pb
        LEFT JOIN v_fixtures_epl f ON f.fixture_id = pb.fixture_id
        WHERE pb.settlement_status = 'pending'
          AND f.status = 'final'
        """,
    ).fetchall()

    if not rows:
        _LOG.info("settlement: no pending bets on final fixtures")
        return {
            "n_settled": 0,
            "n_won": 0,
            "n_lost": 0,
            "n_skipped_no_result": 0,
            "n_skipped_unsupported_market": 0,
            "total_pnl_gbp": Decimal("0.00"),
        }

    n_settled = 0
    n_won = 0
    n_lost = 0
    n_skipped_no_result = 0
    n_skipped_unsupported = 0
    total_pnl = Decimal("0.00")
    settled_at = datetime.now(tz=UTC)

    for (
        decision_id,
        fixture_id,
        market,
        selection,
        stake_gbp,
        odds_at_decision,
        _status,
        home_score,
        away_score,
        result_ft,
    ) in rows:
        market_conditions = _WIN_CONDITION.get(market)
        if market_conditions is None:
            _LOG.warning(
                "settlement: unsupported market %r for decision_id=%s — skipping",
                market,
                decision_id,
            )
            n_skipped_unsupported += 1
            continue

        win_condition = market_conditions.get(selection)
        if win_condition is None:
            _LOG.warning(
                "settlement: unsupported selection %r in market %r for decision_id=%s",
                selection,
                market,
                decision_id,
            )
            n_skipped_unsupported += 1
            continue

        if home_score is None or away_score is None or result_ft is None:
            _LOG.info(
                "settlement: fixture %s marked final but scores missing — skipping %s",
                fixture_id,
                decision_id,
            )
            n_skipped_no_result += 1
            continue

        is_winner = _evaluate_win(win_condition, home_score, away_score, result_ft)
        stake = Decimal(str(stake_gbp))
        odds = float(odds_at_decision)

        if is_winner:
            pnl = stake * Decimal(str(odds - 1.0))
            n_won += 1
        else:
            pnl = -stake
            n_lost += 1

        total_pnl += pnl
        n_settled += 1

        if dry_run:
            _LOG.info(
                "settlement [DRY RUN]: %s %s/%s/%s stake=%.2f odds=%.2f winner=%s pnl=%.2f",
                decision_id,
                fixture_id,
                market,
                selection,
                float(stake),
                odds,
                is_winner,
                float(pnl),
            )
            continue

        con.execute(
            """
            UPDATE paper_bets
            SET settlement_status = ?,
                settled_at        = ?,
                pnl_gbp           = ?
            WHERE decision_id = ?
            """,
            [
                "settled",
                settled_at,
                float(pnl),
                decision_id,
            ],
        )

    _LOG.info(
        "settlement: settled=%d won=%d lost=%d skipped_no_result=%d "
        "skipped_unsupported=%d total_pnl=%.2f",
        n_settled,
        n_won,
        n_lost,
        n_skipped_no_result,
        n_skipped_unsupported,
        float(total_pnl),
    )
    return {
        "n_settled": n_settled,
        "n_won": n_won,
        "n_lost": n_lost,
        "n_skipped_no_result": n_skipped_no_result,
        "n_skipped_unsupported_market": n_skipped_unsupported,
        "total_pnl_gbp": total_pnl,
    }


def _evaluate_win(
    win_condition: str,
    home_score: int | float,
    away_score: int | float,
    result_ft: str,
) -> bool:
    """Evaluate a WIN_CONDITION string against actual match results.

    Supported conditions (see _WIN_CONDITION above):
      "(home_score_ft + away_score_ft) > 2"
      "(home_score_ft + away_score_ft) <= 2"
      "result_ft = 'H'" / 'D' / 'A'
    """
    home = int(home_score)
    away = int(away_score)
    total = home + away
    result = str(result_ft).strip().upper()

    if win_condition == "(home_score_ft + away_score_ft) > 2":
        return total > 2
    if win_condition == "(home_score_ft + away_score_ft) <= 2":
        return total <= 2
    if win_condition == "result_ft = 'H'":
        return result == "H"
    if win_condition == "result_ft = 'D'":
        return result == "D"
    if win_condition == "result_ft = 'A'":
        return result == "A"

    _LOG.warning("settlement: unknown win_condition %r — treating as loss", win_condition)
    return False


if __name__ == "__main__":
    import duckdb as _duckdb

    from footy_ev.db import apply_migrations, apply_views

    _con = _duckdb.connect(":memory:")
    apply_migrations(_con)
    apply_views(_con)
    result = settle_pending_bets(_con, dry_run=True)
    print(f"smoke: settle_pending_bets (empty DB) → {result}")
