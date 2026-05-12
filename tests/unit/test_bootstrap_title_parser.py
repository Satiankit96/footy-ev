"""Unit tests for _parse_teams_from_title and _strip_title_suffix.

Title formats observed on Kalshi demo (2026-05-12 capture):
  "West Ham at Leeds United: Total Goals"  → US convention: away=X, home=Y
  "Tottenham at Chelsea: Totals"
  "Arsenal vs Liverpool - Total Goals"      → X=home, Y=away
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from bootstrap_kalshi_aliases import (  # type: ignore[import-not-found] # noqa: E402
    FUZZY_ACCEPT_THRESHOLD,
    _fuzzy_match_team,
    _load_canonical_teams,
    _parse_teams_from_title,
    _strip_title_suffix,
)

from footy_ev.db import apply_migrations, apply_views  # noqa: E402


def test_at_format_total_goals_resolves_away_home() -> None:
    # "X at Y" → X=away, Y=home (returned as (home, away))
    result = _parse_teams_from_title("West Ham at Leeds United: Total Goals")
    assert result == ("Leeds United", "West Ham")


def test_at_format_totals_suffix_stripped() -> None:
    result = _parse_teams_from_title("Tottenham at Chelsea: Totals")
    assert result == ("Chelsea", "Tottenham")


def test_vs_format_dash_total_goals_resolves_home_away() -> None:
    # "X vs Y" → X=home, Y=away
    result = _parse_teams_from_title("Arsenal vs Liverpool - Total Goals")
    assert result == ("Arsenal", "Liverpool")


def test_strip_suffix_handles_all_variants() -> None:
    cases = [
        ("Arsenal vs Liverpool: Total Goals", "Arsenal vs Liverpool"),
        ("Arsenal vs Liverpool: Totals", "Arsenal vs Liverpool"),
        ("Arsenal vs Liverpool - Total Goals", "Arsenal vs Liverpool"),
        ("Arsenal vs Liverpool - Totals", "Arsenal vs Liverpool"),
        ("Arsenal vs Liverpool Total Goals", "Arsenal vs Liverpool"),
        ("Arsenal vs Liverpool Totals", "Arsenal vs Liverpool"),
        # case-insensitive
        ("Arsenal vs Liverpool: TOTAL GOALS", "Arsenal vs Liverpool"),
    ]
    for raw, expected in cases:
        assert _strip_title_suffix(raw) == expected, f"input {raw!r}"


@pytest.fixture
def warehouse_with_teams(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    apply_migrations(con)
    apply_views(con)
    return con


def test_fuzzy_match_resolves_canonical_team(
    warehouse_with_teams: duckdb.DuckDBPyConnection,
) -> None:
    # Migration 012 seeds 20 EPL teams in team_aliases (source='kalshi_code').
    # team_aliases(source='football_data') has the actual canonical names
    # (e.g. "Arsenal", "Liverpool") that the fuzzy matcher operates over.
    # Seed a minimal set so the fixture is self-contained.
    from datetime import datetime

    for raw_name, team_id in [
        ("Arsenal", "arsenal"),
        ("Liverpool", "liverpool"),
        ("Chelsea", "chelsea"),
        ("Tottenham", "tottenham"),
    ]:
        con = warehouse_with_teams
        con.execute(
            "INSERT OR IGNORE INTO team_aliases (source, raw_name, team_id, "
            "confidence, resolved_at) VALUES ('football_data', ?, ?, 'manual', ?)",
            [raw_name, team_id, datetime(2026, 1, 1)],
        )
    canonical = _load_canonical_teams(warehouse_with_teams)
    names = list(canonical.keys())
    # Slight noise: "Arsenal FC" should still match "Arsenal" at high score.
    matches = _fuzzy_match_team("Arsenal FC", names, threshold=75)
    assert matches, "expected at least one fuzzy match"
    assert matches[0][1] >= FUZZY_ACCEPT_THRESHOLD
    assert canonical[matches[0][0]] == "arsenal"
