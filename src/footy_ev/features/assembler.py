"""SQL feature assembler for XGBoost O/U 2.5 model.

Builds a Polars DataFrame of FEATURE_NAMES for a list of fixture_ids.
Two modes:
  - "pit": training (PIT-correct window functions, ROWS BETWEEN N PRECEDING AND 1 PRECEDING)
  - "snapshot": test-time (GROUP BY aggregation from all history before as_of)

xg_skellam_p_over is the stacked baseline prediction: most recent model_predictions
row for the given xg_skellam_run_id where as_of < train_cutoff, selection='over'.
Defaults to 0.5 when absent (e.g. fixture has no xG baseline prediction yet).

Fixtures with fewer than the window size of prior matches get NULL rolling stats;
XGBoost handles NaN natively.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import duckdb
import polars as pl

FEATURE_NAMES: list[str] = [
    "home_xg_for_5",
    "away_xg_for_5",
    "home_xg_against_5",
    "away_xg_against_5",
    "home_goals_for_5",
    "away_goals_for_5",
    "home_goals_against_5",
    "away_goals_against_5",
    "home_win_rate_10",
    "away_win_rate_10",
    "home_draw_rate_10",
    "away_draw_rate_10",
    "home_ppg_10",
    "away_ppg_10",
    "xg_skellam_p_over",
]

_EMPTY_SCHEMA = {"fixture_id": pl.Utf8, **dict.fromkeys(FEATURE_NAMES, pl.Float64)}


def build_feature_matrix(
    con: duckdb.DuckDBPyConnection,
    fixture_ids: list[str],
    as_of: datetime,
    xg_skellam_run_id: str,
    *,
    fixtures_view: str = "v_fixtures_epl",
    mode: Literal["pit", "snapshot"] = "snapshot",
    feature_subset: list[str] | None = None,
) -> pl.DataFrame:
    """Build a feature matrix with one row per fixture_id.

    Args:
        con: open DuckDB connection.
        fixture_ids: fixtures to featurize.
        as_of: cutoff timestamp; historical data is strictly before this.
        xg_skellam_run_id: run_id of the locked xG-Skellam baseline in
            model_predictions; used for the stacked xg_skellam_p_over feature.
        fixtures_view: view name; override for unit tests.
        mode: "pit" uses window functions for PIT-correct training features;
              "snapshot" aggregates last-N matches for test-time features.
        feature_subset: if not None, project the result to ["fixture_id"] +
            feature_subset. Names must be a subset of FEATURE_NAMES; order is
            preserved as given. Used by diagnostic ablation backtests.

    Returns:
        DataFrame with columns ["fixture_id"] + (feature_subset or FEATURE_NAMES).
        Rows are only present when the fixture can be joined to both teams'
        rolling stats (i.e. both teams have at least 1 prior match). Fixtures
        with insufficient history get NaN for the rolling features.

    Raises:
        ValueError: if feature_subset contains names not in FEATURE_NAMES.
    """
    if feature_subset is not None:
        unknown = [c for c in feature_subset if c not in FEATURE_NAMES]
        if unknown:
            raise ValueError(
                f"feature_subset contains unknown names: {unknown}. Valid: {FEATURE_NAMES}"
            )

    if not fixture_ids:
        cols_out = ["fixture_id"] + (feature_subset or FEATURE_NAMES)
        empty_schema = {c: (pl.Utf8 if c == "fixture_id" else pl.Float64) for c in cols_out}
        return pl.DataFrame(schema=empty_schema)

    if mode == "pit":
        df = _build_pit(con, fixture_ids, as_of, xg_skellam_run_id, fixtures_view)
    else:
        df = _build_snapshot(con, fixture_ids, as_of, xg_skellam_run_id, fixtures_view)

    if feature_subset is not None:
        df = df.select(["fixture_id"] + feature_subset)
    return df


# ---------------------------------------------------------------------------
# Shared CTE fragments (parameterised by fixtures_view)
# ---------------------------------------------------------------------------

_TEAM_EVENTS_CTE = """
team_events AS (
    SELECT
        home_team_id                             AS team_id,
        fixture_id,
        kickoff_utc,
        home_xg                                  AS xg_for,
        away_xg                                  AS xg_against,
        CAST(home_score_ft AS DOUBLE)            AS goals_for,
        CAST(away_score_ft AS DOUBLE)            AS goals_against,
        CASE WHEN home_score_ft > away_score_ft  THEN 3.0
             WHEN home_score_ft = away_score_ft  THEN 1.0
             ELSE 0.0 END                        AS pts,
        CASE WHEN home_score_ft > away_score_ft  THEN 1.0 ELSE 0.0 END AS is_win,
        CASE WHEN home_score_ft = away_score_ft  THEN 1.0 ELSE 0.0 END AS is_draw
    FROM {fv}
    WHERE status = 'final' AND kickoff_utc < ?
    UNION ALL
    SELECT
        away_team_id                             AS team_id,
        fixture_id,
        kickoff_utc,
        away_xg                                  AS xg_for,
        home_xg                                  AS xg_against,
        CAST(away_score_ft AS DOUBLE)            AS goals_for,
        CAST(home_score_ft AS DOUBLE)            AS goals_against,
        CASE WHEN away_score_ft > home_score_ft  THEN 3.0
             WHEN away_score_ft = home_score_ft  THEN 1.0
             ELSE 0.0 END                        AS pts,
        CASE WHEN away_score_ft > home_score_ft  THEN 1.0 ELSE 0.0 END AS is_win,
        CASE WHEN away_score_ft = home_score_ft  THEN 1.0 ELSE 0.0 END AS is_draw
    FROM {fv}
    WHERE status = 'final' AND kickoff_utc < ?
)
"""

_XG_STACKED_CTE = """
xg_stacked AS (
    SELECT inner_mp.fixture_id, inner_mp.p_raw AS xg_skellam_p_over
    FROM (
        SELECT
            mp.fixture_id,
            mp.p_raw,
            ROW_NUMBER() OVER (
                PARTITION BY mp.fixture_id ORDER BY mp.as_of DESC
            ) AS rn
        FROM model_predictions mp
        WHERE mp.run_id    = ?
          AND mp.market    = 'ou_2.5'
          AND mp.selection = 'over'
          AND mp.as_of     <= ?
    ) inner_mp
    WHERE inner_mp.rn = 1
)
"""

_SELECT_TAIL = """
SELECT
    f.fixture_id,
    h.xg_for_5        AS home_xg_for_5,
    a.xg_for_5        AS away_xg_for_5,
    h.xg_against_5    AS home_xg_against_5,
    a.xg_against_5    AS away_xg_against_5,
    h.goals_for_5     AS home_goals_for_5,
    a.goals_for_5     AS away_goals_for_5,
    h.goals_against_5 AS home_goals_against_5,
    a.goals_against_5 AS away_goals_against_5,
    h.win_rate_10     AS home_win_rate_10,
    a.win_rate_10     AS away_win_rate_10,
    h.draw_rate_10    AS home_draw_rate_10,
    a.draw_rate_10    AS away_draw_rate_10,
    h.ppg_10          AS home_ppg_10,
    a.ppg_10          AS away_ppg_10,
    COALESCE(xs.xg_skellam_p_over, 0.5) AS xg_skellam_p_over
FROM {fv} f
{join_h}
{join_a}
LEFT JOIN xg_stacked xs ON xs.fixture_id = f.fixture_id
WHERE f.fixture_id = ANY(?)
"""


def _build_pit(
    con: duckdb.DuckDBPyConnection,
    fixture_ids: list[str],
    as_of: datetime,
    xg_skellam_run_id: str,
    fixtures_view: str,
) -> pl.DataFrame:
    fv = fixtures_view
    rolling_cte = """
rolling AS (
    SELECT
        team_id,
        fixture_id,
        AVG(xg_for)        OVER w5  AS xg_for_5,
        AVG(xg_against)    OVER w5  AS xg_against_5,
        AVG(goals_for)     OVER w5  AS goals_for_5,
        AVG(goals_against) OVER w5  AS goals_against_5,
        AVG(is_win)        OVER w10 AS win_rate_10,
        AVG(is_draw)       OVER w10 AS draw_rate_10,
        AVG(pts)           OVER w10 / 3.0 AS ppg_10
    FROM team_events
    WINDOW
        w5  AS (PARTITION BY team_id ORDER BY kickoff_utc
                ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING),
        w10 AS (PARTITION BY team_id ORDER BY kickoff_utc
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING)
)
"""
    join_h = "JOIN rolling h ON h.team_id = f.home_team_id AND h.fixture_id = f.fixture_id"
    join_a = "JOIN rolling a ON a.team_id = f.away_team_id AND a.fixture_id = f.fixture_id"

    sql = (
        "WITH "
        + _TEAM_EVENTS_CTE.format(fv=fv)
        + ",\n"
        + rolling_cte
        + ",\n"
        + _XG_STACKED_CTE
        + "\n"
        + _SELECT_TAIL.format(fv=fv, join_h=join_h, join_a=join_a)
    )
    params = [as_of, as_of, xg_skellam_run_id, as_of, fixture_ids]
    out: pl.DataFrame = con.execute(sql, params).pl()
    return out


def _build_snapshot(
    con: duckdb.DuckDBPyConnection,
    fixture_ids: list[str],
    as_of: datetime,
    xg_skellam_run_id: str,
    fixtures_view: str,
) -> pl.DataFrame:
    fv = fixtures_view
    stats_cte = """
team_ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY kickoff_utc DESC) AS rn
    FROM team_events
),
team_stats AS (
    SELECT
        team_id,
        AVG(CASE WHEN rn <= 5  THEN xg_for        END) AS xg_for_5,
        AVG(CASE WHEN rn <= 5  THEN xg_against    END) AS xg_against_5,
        AVG(CASE WHEN rn <= 5  THEN goals_for     END) AS goals_for_5,
        AVG(CASE WHEN rn <= 5  THEN goals_against END) AS goals_against_5,
        AVG(CASE WHEN rn <= 10 THEN is_win        END) AS win_rate_10,
        AVG(CASE WHEN rn <= 10 THEN is_draw       END) AS draw_rate_10,
        AVG(CASE WHEN rn <= 10 THEN pts           END) / 3.0 AS ppg_10
    FROM team_ranked
    GROUP BY team_id
)
"""

    # Alias team_stats columns to match rolling CTE column names used in _SELECT_TAIL
    # For snapshot mode: join is on team_id only (no fixture_id constraint)
    join_h_snap = "JOIN team_stats h ON h.team_id = f.home_team_id"
    join_a_snap = "JOIN team_stats a ON a.team_id = f.away_team_id"

    select_snap = f"""
SELECT
    f.fixture_id,
    h.xg_for_5        AS home_xg_for_5,
    a.xg_for_5        AS away_xg_for_5,
    h.xg_against_5    AS home_xg_against_5,
    a.xg_against_5    AS away_xg_against_5,
    h.goals_for_5     AS home_goals_for_5,
    a.goals_for_5     AS away_goals_for_5,
    h.goals_against_5 AS home_goals_against_5,
    a.goals_against_5 AS away_goals_against_5,
    h.win_rate_10     AS home_win_rate_10,
    a.win_rate_10     AS away_win_rate_10,
    h.draw_rate_10    AS home_draw_rate_10,
    a.draw_rate_10    AS away_draw_rate_10,
    h.ppg_10          AS home_ppg_10,
    a.ppg_10          AS away_ppg_10,
    COALESCE(xs.xg_skellam_p_over, 0.5) AS xg_skellam_p_over
FROM {fv} f
{join_h_snap}
{join_a_snap}
LEFT JOIN xg_stacked xs ON xs.fixture_id = f.fixture_id
WHERE f.fixture_id = ANY(?)
"""

    sql = (
        "WITH "
        + _TEAM_EVENTS_CTE.format(fv=fv)
        + ",\n"
        + stats_cte
        + ",\n"
        + _XG_STACKED_CTE
        + "\n"
        + select_snap
    )
    params = [as_of, as_of, xg_skellam_run_id, as_of, fixture_ids]
    out: pl.DataFrame = con.execute(sql, params).pl()
    return out


if __name__ == "__main__":
    print("assembler smoke: import OK, FEATURE_NAMES =", FEATURE_NAMES)
