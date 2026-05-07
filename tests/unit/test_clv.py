"""Unit tests for CLV / closing-line edge computation.

Builds a synthetic in-memory warehouse with model_predictions +
v_pinnacle_close_epl + v_fixtures_epl tables (no need for full schema).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import duckdb
import pytest

from footy_ev.eval.clv import compute_clv
from footy_ev.eval.devig import devig_shin


def _make_test_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE model_predictions (
            prediction_id  VARCHAR PRIMARY KEY,
            run_id         VARCHAR NOT NULL,
            fixture_id     VARCHAR NOT NULL,
            market         VARCHAR NOT NULL DEFAULT '1x2',
            selection      VARCHAR NOT NULL,
            p_raw          DOUBLE NOT NULL,
            p_calibrated   DOUBLE NOT NULL,
            as_of          TIMESTAMP NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE v_pinnacle_close_epl (
            fixture_id              VARCHAR,
            match_date              DATE,
            season                  VARCHAR,
            market                  VARCHAR DEFAULT '1x2',
            selection               VARCHAR,
            pinnacle_close_decimal  DOUBLE,
            is_winner               BOOLEAN
        )
    """)
    con.execute("""
        CREATE TABLE v_fixtures_epl (
            fixture_id  VARCHAR PRIMARY KEY,
            season      VARCHAR,
            result_ft   VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE clv_evaluations (
            evaluation_id           VARCHAR PRIMARY KEY,
            run_id                  VARCHAR NOT NULL,
            prediction_id           VARCHAR NOT NULL,
            fixture_id              VARCHAR NOT NULL,
            market                  VARCHAR,
            selection               VARCHAR NOT NULL,
            p_raw                   DOUBLE NOT NULL,
            p_calibrated            DOUBLE NOT NULL,
            pinnacle_close_decimal  DOUBLE NOT NULL,
            pinnacle_q_devigged     DOUBLE NOT NULL,
            devig_method            VARCHAR NOT NULL,
            edge_at_close           DOUBLE NOT NULL,
            is_winner               BOOLEAN NOT NULL,
            would_have_bet          BOOLEAN NOT NULL,
            evaluated_at            TIMESTAMP NOT NULL
        )
    """)
    return con


def _seed_fixture(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    fixture_id: str,
    season: str,
    p_model: tuple[float, ...],
    odds: tuple[float, ...],
    result_ft: str,
    *,
    market: str = "1x2",
    selections: tuple[str, ...] = ("home", "draw", "away"),
    pinnacle_present: bool = True,
) -> None:
    for sel, p in zip(selections, p_model, strict=False):
        pid = str(uuid.uuid4())
        con.execute(
            "INSERT INTO model_predictions (prediction_id, run_id, fixture_id, "
            "market, selection, p_raw, p_calibrated, as_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [pid, run_id, fixture_id, market, sel, p, p, datetime(2024, 1, 1)],
        )
    con.execute(
        "INSERT INTO v_fixtures_epl (fixture_id, season, result_ft) VALUES (?, ?, ?)",
        [fixture_id, season, result_ft],
    )
    if pinnacle_present:
        for sel, o in zip(selections, odds, strict=False):
            is_win = (
                (sel == "home" and result_ft == "H")
                or (sel == "draw" and result_ft == "D")
                or (sel == "away" and result_ft == "A")
            )
            con.execute(
                "INSERT INTO v_pinnacle_close_epl (fixture_id, match_date, season, "
                "market, selection, pinnacle_close_decimal, is_winner) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [fixture_id, datetime(2024, 1, 1).date(), season, market, sel, o, is_win],
            )


def test_edge_zero_when_model_equals_market():
    """When p_calibrated == q_devigged for each selection, edge_at_close ≈ 0."""
    con = _make_test_db()
    odds = (2.0, 4.0, 4.0)  # vig-y; sum(1/o) = 1.0 (no vig coincidentally)
    q = devig_shin(odds)  # = (0.5, 0.25, 0.25) under no-vig
    _seed_fixture(con, "r1", "fix1", "2023-2024", q, odds, "H")
    compute_clv(con, "r1", calibrated_probs={})
    # All 3 rows; edge ≈ 0 because p_raw = q_devigged
    rows = con.execute("SELECT edge_at_close FROM clv_evaluations WHERE run_id='r1'").fetchall()
    assert len(rows) == 3
    for (e,) in rows:
        assert abs(e) < 1e-9


def test_edge_positive_when_model_better_on_winner():
    """Model assigns 0.6 to winner; market de-vigged is 0.5 → edge ≈ +0.20."""
    con = _make_test_db()
    odds = (2.0, 4.0, 4.0)  # sum(1/o) = 1.0 → de-vigged q = (0.5, 0.25, 0.25)
    p_model = (0.60, 0.20, 0.20)  # sums to 1
    _seed_fixture(con, "r2", "fix2", "2023-2024", p_model, odds, "H")
    summary = compute_clv(con, "r2", calibrated_probs={})
    winners = con.execute(
        "SELECT edge_at_close FROM clv_evaluations WHERE run_id='r2' AND is_winner = TRUE"
    ).fetchall()
    assert len(winners) == 1
    edge_winner = winners[0][0]
    # 0.60 / 0.50 - 1 = 0.20
    assert edge_winner == pytest.approx(0.20, abs=1e-6)
    assert summary["mean_edge_winners"] == pytest.approx(0.20, abs=1e-6)


def test_skip_when_pinnacle_missing():
    """Fixture with no Pinnacle close → all 3 selections skipped, none written."""
    con = _make_test_db()
    _seed_fixture(
        con,
        "r3",
        "fix3",
        "2023-2024",
        (0.5, 0.3, 0.2),
        (2.0, 3.5, 5.0),
        "H",
        pinnacle_present=False,
    )
    summary = compute_clv(con, "r3", calibrated_probs={})
    assert summary["n_evaluated"] == 0
    assert summary["n_skipped_no_pinnacle"] == 3
    n_clv = con.execute("SELECT COUNT(*) FROM clv_evaluations WHERE run_id='r3'").fetchone()[0]
    assert n_clv == 0


def test_three_rows_per_fixture():
    """Each evaluable fixture writes exactly 3 clv_evaluations rows."""
    con = _make_test_db()
    _seed_fixture(con, "r4", "fix4", "2023-2024", (0.4, 0.3, 0.3), (2.5, 3.5, 3.0), "D")
    _seed_fixture(con, "r4", "fix5", "2023-2024", (0.55, 0.25, 0.20), (1.9, 4.0, 5.0), "A")
    summary = compute_clv(con, "r4", calibrated_probs={})
    assert summary["n_evaluated"] == 6
    rows_per_fix = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT fixture_id, COUNT(*) FROM clv_evaluations WHERE run_id='r4' GROUP BY fixture_id"
        ).fetchall()
    }
    assert rows_per_fix == {"fix4": 3, "fix5": 3}


def test_would_have_bet_threshold():
    """would_have_bet == (edge_at_close > EDGE_THRESHOLD = 0.03)."""
    con = _make_test_db()
    # Set up a market where home-edge is exactly +0.04 (above threshold)
    # and draw/away edges are ~0 (below). odds=(2.0, 4.0, 4.0), q=(0.5, 0.25, 0.25).
    # p=0.52 home → edge = 0.52/0.50 - 1 = 0.04
    _seed_fixture(con, "r5", "fix6", "2023-2024", (0.52, 0.24, 0.24), (2.0, 4.0, 4.0), "H")
    compute_clv(con, "r5", calibrated_probs={})
    rows = con.execute(
        "SELECT selection, edge_at_close, would_have_bet FROM clv_evaluations WHERE run_id='r5'"
    ).fetchall()
    sel_to = {r[0]: (r[1], r[2]) for r in rows}
    home_edge, home_bet = sel_to["home"]
    assert home_edge == pytest.approx(0.04, abs=1e-6)
    assert home_bet is True
    # Draw/away edges < 0.03 → would_have_bet False
    for sel in ("draw", "away"):
        assert sel_to[sel][1] is False, f"selection {sel} unexpectedly flagged would_have_bet"


def test_calibrated_overrides_raw_when_provided():
    """calibrated_probs[prediction_id] takes precedence over p_raw."""
    con = _make_test_db()
    _seed_fixture(con, "r6", "fix7", "2023-2024", (0.50, 0.25, 0.25), (2.0, 4.0, 4.0), "H")
    home_pred = con.execute(
        "SELECT prediction_id FROM model_predictions WHERE run_id='r6' AND selection='home'"
    ).fetchone()[0]
    # Force calibrated home prob to 0.60 → expect edge = 0.60/0.50 - 1 = 0.20
    compute_clv(con, "r6", calibrated_probs={home_pred: 0.60})
    home_edge = con.execute(
        "SELECT edge_at_close FROM clv_evaluations WHERE run_id='r6' AND selection='home'"
    ).fetchone()[0]
    assert home_edge == pytest.approx(0.20, abs=1e-6)


def test_empty_run_returns_empty_summary():
    con = _make_test_db()
    summary = compute_clv(con, "nonexistent", calibrated_probs={})
    assert summary["n_evaluated"] == 0
    assert summary["n_skipped_no_pinnacle"] == 0


def test_compute_clv_ou_2_5_market():
    """O/U 2.5 market: 2 selections per fixture, devigged correctly."""
    con = _make_test_db()
    # odds=(2.0, 2.0), fair=0.5 each (no vig). p_model=(0.6, 0.4).
    # edge_over = 0.6 / 0.5 - 1 = 0.20; edge_under = 0.4 / 0.5 - 1 = -0.20
    _seed_fixture(
        con,
        "ou_run",
        "fix_ou",
        "2023-2024",
        p_model=(0.60, 0.40),
        odds=(2.0, 2.0),
        result_ft="H",  # result_ft used only for 1x2; ignored in O/U
        market="ou_2.5",
        selections=("over", "under"),
    )
    # Set is_winner manually for over selection (we can't derive from result_ft here).
    # Override the row that was written with wrong is_winner for ou_2.5.
    con.execute(
        "UPDATE v_pinnacle_close_epl SET is_winner = TRUE  WHERE fixture_id='fix_ou' AND selection='over'"
    )
    con.execute(
        "UPDATE v_pinnacle_close_epl SET is_winner = FALSE WHERE fixture_id='fix_ou' AND selection='under'"
    )
    summary = compute_clv(con, "ou_run", calibrated_probs={})
    assert summary["n_evaluated"] == 2, f"expected 2 evaluated rows, got {summary['n_evaluated']}"
    rows = con.execute(
        "SELECT selection, edge_at_close, is_winner FROM clv_evaluations "
        "WHERE run_id='ou_run' ORDER BY selection"
    ).fetchall()
    sel_to = {r[0]: (r[1], r[2]) for r in rows}
    assert "over" in sel_to and "under" in sel_to
    assert sel_to["over"][0] == pytest.approx(0.20, abs=1e-6)
    assert sel_to["under"][0] == pytest.approx(-0.20, abs=1e-6)
