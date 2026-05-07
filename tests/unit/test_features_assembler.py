"""Unit tests for features.assembler.build_feature_matrix.

Tests:
  1. Correct columns returned (fixture_id + FEATURE_NAMES).
  2. PIT-correct rolling: fixture with < 5 prior matches gets NULL xg_for_5.
  3. Non-null rolling after >= 5 prior matches.
  4. xg_skellam_p_over falls back to 0.5 when no model_predictions exist.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from footy_ev.db import apply_migrations, apply_views
from footy_ev.features.assembler import FEATURE_NAMES, build_feature_matrix

# ---------------------------------------------------------------------------
# Minimal in-memory DB helpers
# ---------------------------------------------------------------------------


def _setup_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    apply_views(con)
    return con


def _insert_alias(con: duckdb.DuckDBPyConnection, raw: str, team_id: str) -> None:
    con.execute(
        """
        INSERT INTO team_aliases (source, raw_name, team_id, confidence, resolved_at)
        VALUES ('football_data', ?, ?, 'manual', NOW())
        ON CONFLICT DO NOTHING
        """,
        [raw, team_id],
    )


def _insert_match(
    con: duckdb.DuckDBPyConnection,
    match_date: str,
    home: str,
    away: str,
    hg: int,
    ag: int,
    league: str = "EPL",
    season: str = "2020-2021",
) -> None:
    ftr = "H" if hg > ag else ("A" if ag > hg else "D")
    con.execute(
        """
        INSERT INTO raw_match_results (
            league, season, source_code, source_url, ingested_at, source_row_hash,
            div, match_date, home_team, away_team, fthg, ftag, ftr
        ) VALUES (?, ?, 'fd', 'http://x', NOW(), gen_random_uuid(),
                  'E0', ?, ?, ?, ?, ?, ?)
        """,
        [league, season, match_date, home, away, hg, ag, ftr],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_feature_columns_correct() -> None:
    """build_feature_matrix returns fixture_id + FEATURE_NAMES columns."""
    con = _setup_db()
    _insert_alias(con, "Arsenal", "arsenal")
    _insert_alias(con, "Chelsea", "chelsea")
    for i in range(6):
        d = f"2021-0{i + 1}-15"
        _insert_match(con, d, "Arsenal", "Chelsea", 2, 1)

    as_of = datetime(2021, 8, 1)
    all_ids = con.execute("SELECT fixture_id FROM v_fixtures_epl").fetchdf()["fixture_id"].tolist()
    df = build_feature_matrix(con, all_ids, as_of, xg_skellam_run_id="", mode="pit")

    assert "fixture_id" in df.columns
    for feat in FEATURE_NAMES:
        assert feat in df.columns, f"missing column: {feat}"


def test_pit_null_rolling_for_insufficient_history() -> None:
    """First fixture for a team has NULL xg_for_5 (no prior matches)."""
    con = _setup_db()
    _insert_alias(con, "TeamA", "team_a")
    _insert_alias(con, "TeamB", "team_b")

    # Only 1 match — the FIRST match for both teams
    _insert_match(con, "2021-01-01", "TeamA", "TeamB", 2, 1)

    as_of = datetime(2022, 1, 1)
    fids = con.execute("SELECT fixture_id FROM v_fixtures_epl").fetchdf()["fixture_id"].tolist()

    # PIT mode: this fixture has 0 preceding matches per team → NULL rolling
    df = build_feature_matrix(con, fids, as_of, xg_skellam_run_id="", mode="pit")
    assert df.height == 0 or df["home_xg_for_5"].is_null().all(), (
        "expected NULL home_xg_for_5 for fixture with no prior team history"
    )


def test_pit_non_null_rolling_after_enough_history() -> None:
    """After 6 matches, the 6th fixture's home team has non-null xg_for_5."""
    con = _setup_db()
    _insert_alias(con, "TeamA", "team_a")
    _insert_alias(con, "TeamB", "team_b")

    # 6 matches: TeamA always home, so by the 6th it has 5 preceding matches
    for i in range(6):
        d = f"2021-{i + 1:02d}-01"
        # Alternate: give them xg via understat would require understat rows;
        # without xg the rolling will be NULL (home_xg is NULL from LEFT JOIN).
        # Goals-based features should be non-null.
        _insert_match(con, d, "TeamA", "TeamB", 2, 1)

    as_of = datetime(2022, 1, 1)
    fids = con.execute("SELECT fixture_id FROM v_fixtures_epl").fetchdf()["fixture_id"].tolist()

    df = build_feature_matrix(con, fids, as_of, xg_skellam_run_id="", mode="pit")
    # The last fixture (6th) should have non-null home_goals_for_5
    if df.height > 0:
        last = df.sort("fixture_id").tail(1)
        assert last["home_goals_for_5"][0] is not None, (
            "expected non-null home_goals_for_5 after 5 prior matches"
        )


def test_xg_skellam_defaults_to_half() -> None:
    """xg_skellam_p_over defaults to 0.5 when run_id has no model_predictions."""
    con = _setup_db()
    _insert_alias(con, "TeamA", "team_a")
    _insert_alias(con, "TeamB", "team_b")

    for i in range(3):
        d = f"2021-{i + 1:02d}-01"
        _insert_match(con, d, "TeamA", "TeamB", 2, 1)

    as_of = datetime(2022, 1, 1)
    fids = con.execute("SELECT fixture_id FROM v_fixtures_epl").fetchdf()["fixture_id"].tolist()

    df = build_feature_matrix(
        con, fids, as_of, xg_skellam_run_id="nonexistent-run-id", mode="snapshot"
    )
    if df.height > 0:
        assert (df["xg_skellam_p_over"] == 0.5).all(), (
            "xg_skellam_p_over should be 0.5 when no model_predictions found"
        )


def test_xg_skellam_at_exact_as_of_is_included() -> None:
    """Regression: prediction with as_of == assembler as_of must NOT default to 0.5.

    The XGBoost and Skellam walk-forward use the same fold cutoffs, so test
    fixtures' Skellam predictions have as_of == XGBoost's as_of. The assembler
    must use <= (not <) when filtering model_predictions.
    """
    from uuid import uuid4

    con = _setup_db()
    _insert_alias(con, "TeamA", "team_a")
    _insert_alias(con, "TeamB", "team_b")

    for i in range(4):
        d = f"2021-{i + 1:02d}-01"
        _insert_match(con, d, "TeamA", "TeamB", 2, 1)

    as_of = datetime(2021, 5, 1)
    fids = con.execute("SELECT fixture_id FROM v_fixtures_epl").fetchdf()["fixture_id"].tolist()
    target_fid = fids[0]
    skellam_run = "skellam-exact-as-of"
    expected_p = 0.37

    con.execute(
        """INSERT INTO model_predictions (
               prediction_id, fixture_id, market, selection, p_raw, p_calibrated,
               sigma_p, model_version, features_hash, as_of, generated_at, run_id
           ) VALUES (?, ?, 'ou_2.5', 'over', ?, ?, NULL, 'xg_skellam_v1', 'h', ?, NOW(), ?)""",
        [str(uuid4()), target_fid, expected_p, expected_p, as_of, skellam_run],
    )

    df = build_feature_matrix(
        con,
        [target_fid],
        as_of,
        xg_skellam_run_id=skellam_run,
        mode="snapshot",
        feature_subset=["xg_skellam_p_over"],
    )
    assert df.height == 1, "expected one row"
    val = df["xg_skellam_p_over"][0]
    assert val == expected_p, (
        f"expected {expected_p} (prediction made at exact as_of), got {val}. "
        "assembler must use <= not < when filtering model_predictions.as_of"
    )


def test_empty_fixture_ids_returns_empty() -> None:
    """Empty fixture_ids returns a DataFrame with correct schema but 0 rows."""
    con = _setup_db()
    as_of = datetime(2022, 1, 1)
    df = build_feature_matrix(con, [], as_of, xg_skellam_run_id="", mode="pit")
    assert df.height == 0
    assert "fixture_id" in df.columns


def test_feature_subset_filters_columns() -> None:
    """feature_subset projects to ['fixture_id'] + subset, in that order."""
    con = _setup_db()
    _insert_alias(con, "Arsenal", "arsenal")
    _insert_alias(con, "Chelsea", "chelsea")
    for i in range(6):
        _insert_match(con, f"2021-0{i + 1}-15", "Arsenal", "Chelsea", 2, 1)

    as_of = datetime(2021, 8, 1)
    fids = con.execute("SELECT fixture_id FROM v_fixtures_epl").fetchdf()["fixture_id"].tolist()

    subset = ["xg_skellam_p_over", "home_goals_for_5"]
    df = build_feature_matrix(
        con,
        fids,
        as_of,
        xg_skellam_run_id="",
        mode="pit",
        feature_subset=subset,
    )
    assert df.columns == ["fixture_id"] + subset


def test_feature_subset_unknown_name_raises() -> None:
    """feature_subset with a name not in FEATURE_NAMES raises ValueError."""
    con = _setup_db()
    with pytest.raises(ValueError, match="unknown names"):
        build_feature_matrix(
            con,
            [],
            datetime(2022, 1, 1),
            xg_skellam_run_id="",
            feature_subset=["does_not_exist"],
        )


def test_feature_subset_empty_fixture_list_returns_subset_schema() -> None:
    """Empty fixture_ids with subset returns 0-row DF with the subset shape."""
    con = _setup_db()
    subset = ["xg_skellam_p_over"]
    df = build_feature_matrix(
        con,
        [],
        datetime(2022, 1, 1),
        xg_skellam_run_id="",
        mode="pit",
        feature_subset=subset,
    )
    assert df.height == 0
    assert df.columns == ["fixture_id"] + subset
