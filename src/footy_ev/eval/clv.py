"""Closing-line edge ("CLV proxy") computation against Pinnacle close.

Naming note: column is `edge_at_close` because the strict-CLV form
(bet_decisions.clv_pct = odds_taken/closing_odds - 1) requires a placed
bet's odds_taken, which we don't have until step 3+ adds bet placement.
What we compute here is closer to closing-line edge / ex-ante CLV:

    edge_at_close = p_calibrated * (1 / pinnacle_q_devigged) - 1

i.e. the expected return of a unit stake at the de-vigged closing price,
under the model's calibrated probability. Same go/no-go signal in spirit
(positive in expectation iff the model beats the close), but distinct
column name to avoid future confusion when actual bet_decisions.clv_pct
arrives.

Edge threshold for the would-have-bet subset is 0.03 per BLUE_MAP §8 and
PROJECT_INSTRUCTIONS §7.

Multi-market: groups by (fixture_id, market). Each market has its own
selection ordering and expected row count for devigging.
  1x2    → 3 selections (home, draw, away)
  ou_2.5 → 2 selections (over, under)

Skip-and-log policy mirrors step 1's promoted-team handling: if the
fixture-market group is missing any Pinnacle price or has the wrong row
count, the entire group is skipped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import duckdb
import polars as pl

from footy_ev.eval.devig import DevigMethod, devig

EDGE_THRESHOLD = 0.03  # BLUE_MAP §8 / PROJECT_INSTRUCTIONS §7

# Default selection order for devigging per market.
MARKET_SELECTION_ORDER: dict[str, tuple[str, ...]] = {
    "1x2": ("home", "draw", "away"),
    "ou_2.5": ("over", "under"),
}

DEFAULT_PINNACLE_VIEW = "v_pinnacle_close_epl"
DEFAULT_FIXTURES_VIEW = "v_fixtures_epl"


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compute_clv(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    calibrated_probs: dict[str, float],
    *,
    devig_method: DevigMethod = "shin",
    pinnacle_view: str = DEFAULT_PINNACLE_VIEW,
    fixtures_view: str = DEFAULT_FIXTURES_VIEW,
) -> dict[str, Any]:
    """Compute edge_at_close per prediction and write clv_evaluations.

    Args:
        con: open DuckDB connection.
        run_id: backtest run identifier.
        calibrated_probs: dict[prediction_id -> p_calibrated] from
            calibrate.fit_isotonic_walk_forward. If a prediction_id is
            missing, p_calibrated falls back to p_raw.
        devig_method: 'shin' or 'power'.
        pinnacle_view: source of Pinnacle closing odds (must have market col).
        fixtures_view: source of season + result.

    Returns:
        Aggregate stats dict with keys:
            n_evaluated, n_skipped_no_pinnacle, n_would_have_bet,
            mean_edge_all, median_edge_all,
            mean_edge_winners, median_edge_winners,
            mean_edge_would_have_bet,
            edge_by_season (dict[season -> mean_edge]).
    """
    df = con.execute(
        f"""
        SELECT mp.prediction_id, mp.fixture_id, mp.market, mp.selection,
               mp.p_raw,
               pin.pinnacle_close_decimal, pin.is_winner, f.season
        FROM model_predictions mp
        LEFT JOIN {pinnacle_view} pin
            ON pin.fixture_id = mp.fixture_id
           AND pin.market    = mp.market
           AND pin.selection = mp.selection
        LEFT JOIN {fixtures_view} f
            ON f.fixture_id = mp.fixture_id
        WHERE mp.run_id = ?
        ORDER BY mp.fixture_id, mp.market, mp.selection
        """,
        [run_id],
    ).pl()

    if df.height == 0:
        return _empty_summary()

    rows_to_insert: list[tuple[Any, ...]] = []
    n_skipped = 0
    evaluated_at = _now_naive()

    fixture_market_groups = df.partition_by(
        ["fixture_id", "market"], as_dict=False, maintain_order=True
    )
    for group in fixture_market_groups:
        market = group["market"][0]
        selection_order = MARKET_SELECTION_ORDER.get(market, ("home", "draw", "away"))
        expected = len(selection_order)

        if group.height != expected:
            n_skipped += group.height
            continue

        odds_by_sel: dict[str, float] = {}
        is_winner_by_sel: dict[str, bool] = {}
        rows_by_sel: dict[str, dict[str, Any]] = {}
        any_null = False
        for r in group.iter_rows(named=True):
            sel = r["selection"]
            close_odds = r["pinnacle_close_decimal"]
            if close_odds is None:
                any_null = True
                break
            odds_by_sel[sel] = float(close_odds)
            is_winner_by_sel[sel] = bool(r["is_winner"])
            rows_by_sel[sel] = r

        if any_null or set(odds_by_sel) != set(selection_order):
            n_skipped += group.height
            continue

        odds_tuple = tuple(odds_by_sel[s] for s in selection_order)
        q_tuple = devig(odds_tuple, method=devig_method)
        q_by_sel = dict(zip(selection_order, q_tuple, strict=False))

        for sel in selection_order:
            r = rows_by_sel[sel]
            q = q_by_sel[sel]
            p_cal = calibrated_probs.get(r["prediction_id"], r["p_raw"])
            edge = p_cal * (1.0 / q) - 1.0
            rows_to_insert.append(
                (
                    str(uuid.uuid4()),
                    run_id,
                    r["prediction_id"],
                    r["fixture_id"],
                    market,
                    sel,
                    float(r["p_raw"]),
                    float(p_cal),
                    float(odds_by_sel[sel]),
                    float(q),
                    devig_method,
                    float(edge),
                    bool(is_winner_by_sel[sel]),
                    bool(edge > EDGE_THRESHOLD),
                    evaluated_at,
                )
            )

    if rows_to_insert:
        con.executemany(
            """
            INSERT INTO clv_evaluations (
                evaluation_id, run_id, prediction_id, fixture_id, market,
                selection, p_raw, p_calibrated, pinnacle_close_decimal,
                pinnacle_q_devigged, devig_method, edge_at_close,
                is_winner, would_have_bet, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )

    return _aggregate_summary(con, run_id, n_skipped, fixtures_view)


def _empty_summary() -> dict[str, Any]:
    return {
        "n_evaluated": 0,
        "n_skipped_no_pinnacle": 0,
        "n_would_have_bet": 0,
        "mean_edge_all": float("nan"),
        "median_edge_all": float("nan"),
        "mean_edge_winners": float("nan"),
        "median_edge_winners": float("nan"),
        "mean_edge_would_have_bet": float("nan"),
        "edge_by_season": {},
    }


def _aggregate_summary(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    n_skipped: int,
    fixtures_view: str,
) -> dict[str, Any]:
    eval_df = con.execute(
        "SELECT edge_at_close, is_winner, would_have_bet FROM clv_evaluations WHERE run_id = ?",
        [run_id],
    ).pl()
    n_eval = eval_df.height
    if n_eval == 0:
        s = _empty_summary()
        s["n_skipped_no_pinnacle"] = n_skipped
        return s

    edge = eval_df["edge_at_close"]
    mean_all = float(edge.mean())
    median_all = float(edge.median())

    winners = eval_df.filter(pl.col("is_winner"))
    mean_win = float(winners["edge_at_close"].mean()) if winners.height > 0 else float("nan")
    median_win = float(winners["edge_at_close"].median()) if winners.height > 0 else float("nan")

    bets = eval_df.filter(pl.col("would_have_bet"))
    n_bets = bets.height
    mean_bet = float(bets["edge_at_close"].mean()) if n_bets > 0 else float("nan")

    season_df = con.execute(
        f"""
        SELECT f.season, AVG(c.edge_at_close) AS mean_edge
        FROM clv_evaluations c
        JOIN {fixtures_view} f ON f.fixture_id = c.fixture_id
        WHERE c.run_id = ?
        GROUP BY f.season
        ORDER BY f.season
        """,
        [run_id],
    ).fetchall()
    edge_by_season = {row[0]: float(row[1]) for row in season_df}

    return {
        "n_evaluated": n_eval,
        "n_skipped_no_pinnacle": n_skipped,
        "n_would_have_bet": n_bets,
        "mean_edge_all": mean_all,
        "median_edge_all": median_all,
        "mean_edge_winners": mean_win,
        "median_edge_winners": median_win,
        "mean_edge_would_have_bet": mean_bet,
        "edge_by_season": edge_by_season,
    }
