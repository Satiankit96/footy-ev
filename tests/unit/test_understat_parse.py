"""Unit tests for the Understat parse layer.

These tests exercise:
  - ``extract_matches`` against frozen AJAX fixtures (happy path + null handling)
  - Shape-validation tripwires (non-dict, missing 'dates', short list)
  - JSON decode failure surfacing as ``UnderstatParseError``
  - TZ conversion for EPL across DST boundaries
  - Unknown-key drift handling via ``__pydantic_extra__``
  - Native-bool pinning for ``isResult`` (loud failure on coercion drift)

The two frozen fixtures are committed under
``tests/fixtures/understat/`` — see that directory's README for capture
details and refresh procedure.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from footy_ev.ingestion.understat import UnderstatParseError
from footy_ev.ingestion.understat.parse import (
    MIN_EXPECTED_MATCHES_PER_SEASON,
    convert_kickoff,
    extract_matches,
    parse_payload,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "understat"
COMPLETED_FIXTURE = FIXTURES_DIR / "EPL_2023.json"
IN_PROGRESS_FIXTURE = FIXTURES_DIR / "EPL_2025.json"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _load_fixture(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _valid_match(match_id: str = "1") -> dict[str, Any]:
    """Construct a minimum-valid played-match dict for synthetic-payload tests."""
    return {
        "id": match_id,
        "isResult": True,
        "h": {"id": "92", "title": "Burnley", "short_title": "BUR"},
        "a": {"id": "88", "title": "Manchester City", "short_title": "MCI"},
        "goals": {"h": "0", "a": "3"},
        "xG": {"h": "0.311032", "a": "2.40074"},
        "datetime": "2024-08-11 19:00:00",
        "forecast": {"w": "0.0177", "d": "0.0854", "l": "0.8969"},
    }


def _payload_with_n_matches(n: int) -> dict[str, Any]:
    return {"dates": [_valid_match(str(i)) for i in range(n)]}


# --------------------------------------------------------------------------- #
# Frozen-fixture tests (the primary upstream-drift tripwires)
# --------------------------------------------------------------------------- #
def test_understat_frozen_fixture_completed_season() -> None:
    """Completed season: every match populated, forecast present."""
    payload = _load_fixture(COMPLETED_FIXTURE)
    matches = extract_matches(payload, season="2023-2024", league="EPL")

    assert len(matches) == 380, f"expected 380 EPL matches in 2023-24, got {len(matches)}"
    for m in matches:
        assert m.is_result is True
        assert m.home_goals is not None
        assert m.away_goals is not None
        assert m.home_xg is not None
        assert m.away_xg is not None
        assert m.forecast_home_pct is not None  # populated for played
        assert m.kickoff_local.tzinfo is None  # naive
        assert m.kickoff_utc.tzinfo is not None  # aware
        assert m.kickoff_local.year in {2023, 2024}


def test_understat_frozen_fixture_in_progress_season() -> None:
    """In-progress season: at least one match has goals=None and xG=None and no forecast."""
    payload = _load_fixture(IN_PROGRESS_FIXTURE)
    matches = extract_matches(payload, season="2025-2026", league="EPL")

    assert len(matches) >= MIN_EXPECTED_MATCHES_PER_SEASON

    unplayed = [m for m in matches if not m.is_result]
    assert unplayed, "expected at least one unplayed match in the 2025-26 fixture"

    null_match = next(
        (m for m in unplayed if m.home_goals is None and m.home_xg is None),
        None,
    )
    assert (
        null_match is not None
    ), "expected at least one unplayed match with goals=None AND xG=None"
    assert null_match.away_goals is None
    assert null_match.away_xg is None
    # forecast key is absent on unplayed matches → all three pcts default to None
    assert null_match.forecast_home_pct is None
    assert null_match.forecast_draw_pct is None
    assert null_match.forecast_away_pct is None


# --------------------------------------------------------------------------- #
# Shape-validation tripwires
# --------------------------------------------------------------------------- #
def test_understat_parse_malformed_json_raises() -> None:
    """parse_payload surfaces json.JSONDecodeError as UnderstatParseError."""
    with pytest.raises(UnderstatParseError, match="JSON decode"):
        parse_payload("{not valid json", season="2024-2025", league="EPL")


def test_understat_parse_missing_dates_key_raises() -> None:
    """Dict payload without the 'dates' key raises with diagnostic."""
    payload: dict[str, Any] = {"teams": {}, "players": []}
    with pytest.raises(UnderstatParseError, match="dates"):
        extract_matches(payload, season="2024-2025", league="EPL")


def test_understat_parse_below_min_matches_raises() -> None:
    """R4 sanity: short 'dates' list raises before per-match validation."""
    payload = _payload_with_n_matches(MIN_EXPECTED_MATCHES_PER_SEASON - 1)
    with pytest.raises(UnderstatParseError, match=r"only \d+ entries"):
        extract_matches(payload, season="2024-2025", league="EPL")


# --------------------------------------------------------------------------- #
# TZ conversion tests
# --------------------------------------------------------------------------- #
def test_convert_kickoff_epl_winter() -> None:
    """December: Europe/London is GMT (UTC+0); naive == UTC."""
    naive = datetime(2024, 12, 15, 15, 0, 0)
    utc = convert_kickoff(naive, "EPL")
    assert utc.year == 2024
    assert utc.month == 12
    assert utc.day == 15
    assert utc.hour == 15
    assert utc.minute == 0
    assert utc.utcoffset() is not None
    assert utc.utcoffset().total_seconds() == 0


def test_convert_kickoff_epl_summer() -> None:
    """August: Europe/London is BST (UTC+1); naive 15:00 → UTC 14:00."""
    naive = datetime(2024, 8, 11, 15, 0, 0)
    utc = convert_kickoff(naive, "EPL")
    assert utc.year == 2024
    assert utc.month == 8
    assert utc.day == 11
    assert utc.hour == 14  # BST -> UTC subtracts 1 hour
    assert utc.minute == 0
    assert utc.utcoffset() is not None
    assert utc.utcoffset().total_seconds() == 0


# --------------------------------------------------------------------------- #
# Drift handling — unknown sibling key flows to extras
# --------------------------------------------------------------------------- #
def test_understat_parse_unknown_key_routes_to_extras() -> None:
    """An unknown sibling key inside a match dict survives on __pydantic_extra__."""
    payload = _payload_with_n_matches(MIN_EXPECTED_MATCHES_PER_SEASON)
    payload["dates"][0]["weather"] = "rainy"

    matches = extract_matches(payload, season="2024-2025", league="EPL")
    assert matches[0].__pydantic_extra__ is not None
    assert matches[0].__pydantic_extra__.get("weather") == "rainy"
    # Sanity: known fields still populated correctly
    assert matches[0].is_result is True
    assert matches[0].home_xg == pytest.approx(0.311032)


# --------------------------------------------------------------------------- #
# ADD-2: pin JSON-native-bool expectation for isResult
# --------------------------------------------------------------------------- #
def test_understat_parse_isresult_is_native_bool() -> None:
    """isResult must come through as a Python bool, not str/int.

    StrictBool on the Pydantic field makes Pydantic reject string ``"true"``
    or integer ``1`` — so if Understat ever changes encoding, validation
    fails loudly instead of silently coercing.
    """
    payload = _payload_with_n_matches(MIN_EXPECTED_MATCHES_PER_SEASON)
    matches = extract_matches(payload, season="2024-2025", league="EPL")

    assert matches[0].is_result is True
    assert type(matches[0].is_result) is bool  # not str, not int (bool is technically int-subclass)


def test_understat_parse_isresult_string_rejected() -> None:
    """If isResult ever shows up as a string, StrictBool raises (loud failure)."""
    payload = _payload_with_n_matches(MIN_EXPECTED_MATCHES_PER_SEASON)
    payload["dates"][0]["isResult"] = "true"  # simulate upstream coercion drift

    with pytest.raises(Exception):  # noqa: B017 -- pydantic.ValidationError; we just want it to raise
        extract_matches(payload, season="2024-2025", league="EPL")


# --------------------------------------------------------------------------- #
# Sanity: Pydantic coerces string-typed numerics
# --------------------------------------------------------------------------- #
def test_understat_parse_string_numerics_coerced_to_floats() -> None:
    """Pydantic v2 transparently coerces string-typed source numerics to float/int."""
    payload = _payload_with_n_matches(MIN_EXPECTED_MATCHES_PER_SEASON)
    m = extract_matches(payload, season="2024-2025", league="EPL")[0]
    assert m.home_goals == 0
    assert m.away_goals == 3
    assert m.home_xg == pytest.approx(0.311032)
    assert m.away_xg == pytest.approx(2.40074)
    assert m.forecast_home_pct == pytest.approx(0.0177)
