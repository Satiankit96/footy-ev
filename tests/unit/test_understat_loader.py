"""Unit tests for the Understat loader, drift detection, and view resolution.

All tests run against in-memory DuckDB instances; the production warehouse at
``data/warehouse/footy_ev.duckdb`` must not be touched.

The temporal-alias-join test is the load-bearing one for the
``v_understat_matches`` view's BETWEEN logic. NOTE: the Task 3 spec described
"two alias rows for the SAME raw_name with non-overlapping active_from/
active_to". Migration 003's PK is ``(source, raw_name)``, which makes that
literal scenario impossible. The test below tests the realistic rebrand case
the schema is actually designed for: two alias rows with DIFFERENT raw_names
both mapping to the SAME ``team_id``, with disjoint validity windows. This
exercises the temporal filter without violating the PK. Same intent, schema-
compatible setup.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from footy_ev.db import apply_migrations, apply_views
from footy_ev.ingestion.understat.loader import (
    detect_unmapped_teams,
    load_season,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "understat"
COMPLETED_FIXTURE = FIXTURES_DIR / "EPL_2023.json"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _fresh_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    apply_migrations(con)
    apply_views(con)
    return con


def _valid_match(
    match_id: str,
    *,
    h_raw: str = "Burnley",
    a_raw: str = "Manchester City",
    h_id: str = "92",
    a_id: str = "88",
    kickoff: str = "2024-08-11 19:00:00",
) -> dict[str, Any]:
    return {
        "id": match_id,
        "isResult": True,
        "h": {"id": h_id, "title": h_raw, "short_title": h_raw[:3].upper()},
        "a": {"id": a_id, "title": a_raw, "short_title": a_raw[:3].upper()},
        "goals": {"h": "1", "a": "0"},
        "xG": {"h": "1.5", "a": "0.8"},
        "datetime": kickoff,
        "forecast": {"w": "0.5", "d": "0.3", "l": "0.2"},
    }


def _write_payload(tmp_path: Path, matches: list[dict[str, Any]]) -> Path:
    payload = {"dates": matches, "teams": {}, "players": []}
    p = tmp_path / "synthetic.json"
    p.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return p


def _insert_understat_row(
    con: duckdb.DuckDBPyConnection,
    *,
    match_id: str,
    h_raw: str,
    a_raw: str,
    kickoff_local: str,
    kickoff_utc: str | None = None,
    league: str = "EPL",
    season: str = "2024-2025",
) -> None:
    """Insert one raw_understat_matches row directly (bypass loader)."""
    con.execute(
        """
        INSERT INTO raw_understat_matches (
            league, season, source_code, source_url, ingested_at, source_row_hash,
            understat_match_id, understat_home_id, understat_away_id,
            home_team_raw, away_team_raw,
            kickoff_local, kickoff_utc, is_result
        ) VALUES (?, ?, 'understat', 'http://test/', '2026-04-30 00:00:00', ?,
                  ?, '1', '2', ?, ?, ?, ?, TRUE)
        """,
        [
            league,
            season,
            f"hash-{match_id}",
            match_id,
            h_raw,
            a_raw,
            kickoff_local,
            kickoff_utc or kickoff_local,
        ],
    )


# --------------------------------------------------------------------------- #
# 1. Upsert idempotency
# --------------------------------------------------------------------------- #
def test_understat_loader_upsert_idempotency() -> None:
    """Loading the same fixture twice yields no duplicates."""
    con = _fresh_db()

    report1 = load_season(league="EPL", season="2023-2024", json_path=COMPLETED_FIXTURE, con=con)
    assert report1.inserted == 380
    assert report1.unchanged == 0
    assert report1.updated == 0
    assert report1.total() == 380

    n1 = con.execute("SELECT COUNT(*) FROM raw_understat_matches").fetchone()
    assert n1[0] == 380

    report2 = load_season(league="EPL", season="2023-2024", json_path=COMPLETED_FIXTURE, con=con)
    assert report2.inserted == 0
    assert report2.updated == 0
    assert report2.unchanged == 380
    assert report2.total() == 380

    n2 = con.execute("SELECT COUNT(*) FROM raw_understat_matches").fetchone()
    assert n2[0] == 380, f"expected no duplicates after re-load, got {n2[0]}"


# --------------------------------------------------------------------------- #
# 2. Hash short-circuit
# --------------------------------------------------------------------------- #
def test_understat_loader_hash_short_circuit() -> None:
    """Identical second load short-circuits via source_row_hash match."""
    con = _fresh_db()

    load_season(league="EPL", season="2023-2024", json_path=COMPLETED_FIXTURE, con=con)
    report2 = load_season(league="EPL", season="2023-2024", json_path=COMPLETED_FIXTURE, con=con)
    # Hash unchanged -> all rows fall through to unchanged bucket
    assert report2.unchanged == 380
    assert report2.inserted == 0
    assert report2.updated == 0


# --------------------------------------------------------------------------- #
# 3. Unknown-key drift logging
# --------------------------------------------------------------------------- #
def test_understat_loader_unknown_key_logs_drift(tmp_path: Path) -> None:
    """An unknown sibling key in source data lands in extras AND schema_drift_log."""
    con = _fresh_db()

    matches = [_valid_match(str(i)) for i in range(50)]
    matches[0]["weather"] = "rainy"
    matches[1]["weather"] = "snow"
    matches[2]["referee_xg"] = "0.42"  # second unknown key for variety
    json_path = _write_payload(tmp_path, matches)

    report = load_season(league="EPL", season="2024-2025", json_path=json_path, con=con)

    assert "weather" in report.unknown_keys
    assert "referee_xg" in report.unknown_keys

    drift = con.execute(
        """
        SELECT column_name, source_code, sample_values
        FROM schema_drift_log
        WHERE source_code = 'understat'
        ORDER BY column_name
        """
    ).fetchall()
    drift_cols = {r[0] for r in drift}
    assert {"weather", "referee_xg"} <= drift_cols

    # Sample values for weather should include 'rainy' and 'snow'
    weather_row = next(r for r in drift if r[0] == "weather")
    assert "rainy" in weather_row[2]
    assert "snow" in weather_row[2]

    # Verify extras MAP on the row also carries the unknown key
    extras_row = con.execute(
        "SELECT extras FROM raw_understat_matches WHERE understat_match_id = '0'"
    ).fetchone()
    assert extras_row is not None
    assert extras_row[0].get("weather") == "rainy"


# --------------------------------------------------------------------------- #
# 4. Unmapped-team detection (loader writes raw names; view exposes NULL ids)
# --------------------------------------------------------------------------- #
def test_understat_loader_unmapped_team_detected(tmp_path: Path) -> None:
    """No alias seeded -> v_understat_matches has NULL team_ids; CLI surfaces them."""
    con = _fresh_db()

    matches = [
        _valid_match(
            str(i),
            h_raw="UnknownHome",
            a_raw="UnknownAway",
        )
        for i in range(50)
    ]
    json_path = _write_payload(tmp_path, matches)

    load_season(league="EPL", season="2024-2025", json_path=json_path, con=con)

    unmapped = detect_unmapped_teams(league="EPL", con=con)
    assert sorted(unmapped) == ["UnknownAway", "UnknownHome"]

    null_count = con.execute(
        """
        SELECT COUNT(*) FROM v_understat_matches
        WHERE home_team_id IS NULL OR away_team_id IS NULL
        """
    ).fetchone()[0]
    assert null_count == 50


# --------------------------------------------------------------------------- #
# 5. Temporal alias join (load-bearing view test)
# --------------------------------------------------------------------------- #
def test_understat_loader_temporal_alias_join() -> None:
    """v_understat_matches selects the alias whose [active_from, active_to] window covers kickoff_local.

    Setup: a hypothetical mid-history rebrand where 'OldName' and 'NewName' both
    map to team_id='foo_team' with disjoint windows. A third alias 'Stable'
    has no temporal bounds and applies always.

    Verifies:
      - Match using OldName before the rebrand cutoff -> resolves to foo_team
      - Match using NewName after the rebrand cutoff -> resolves to foo_team
      - Match using OldName AFTER the cutoff -> NULL (alias expired)
      - Stable away team -> always resolves to bar_team
    """
    con = _fresh_db()

    # Three alias rows. PK is (source, raw_name) so all three raw_names differ.
    con.execute(
        """
        INSERT INTO team_aliases
            (source, raw_name, team_id, confidence, resolved_at, active_from, active_to, notes)
        VALUES
            ('understat', 'OldName', 'foo_team', 'manual', '2026-04-30 00:00:00', NULL,                    '2020-08-01 00:00:00', 'pre-rebrand'),
            ('understat', 'NewName', 'foo_team', 'manual', '2026-04-30 00:00:00', '2020-08-01 00:00:00', NULL,                    'post-rebrand'),
            ('understat', 'Stable',  'bar_team', 'manual', '2026-04-30 00:00:00', NULL,                    NULL,                    'always-valid')
        """
    )

    # Three matches.
    _insert_understat_row(
        con,
        match_id="m1",
        h_raw="OldName",
        a_raw="Stable",
        kickoff_local="2019-11-15 15:00:00",
    )
    _insert_understat_row(
        con,
        match_id="m2",
        h_raw="NewName",
        a_raw="Stable",
        kickoff_local="2021-03-10 15:00:00",
    )
    _insert_understat_row(
        con,
        match_id="m3",
        h_raw="OldName",
        a_raw="Stable",
        kickoff_local="2021-03-10 15:00:00",
    )

    rows = con.execute(
        """
        SELECT understat_match_id, home_team_id, away_team_id
        FROM v_understat_matches
        ORDER BY understat_match_id
        """
    ).fetchall()
    assert rows == [
        ("m1", "foo_team", "bar_team"),  # OldName in-window pre-rebrand
        ("m2", "foo_team", "bar_team"),  # NewName in-window post-rebrand
        ("m3", None, "bar_team"),  # OldName out-of-window post-rebrand -> NULL
    ]


# --------------------------------------------------------------------------- #
# Bonus sanity: accounting invariant from the dataclass docstring
# --------------------------------------------------------------------------- #
def test_understat_loader_report_invariant_holds() -> None:
    """LoadReport.total() == inserted + updated + unchanged + rejected."""
    con = _fresh_db()
    report = load_season(league="EPL", season="2023-2024", json_path=COMPLETED_FIXTURE, con=con)
    assert report.total() == report.inserted + report.updated + report.unchanged + report.rejected
