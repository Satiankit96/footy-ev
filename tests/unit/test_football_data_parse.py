"""Unit tests for FootballDataRow parsing."""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from footy_ev.ingestion.football_data.parse import FootballDataRow


def _modern_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Div": "E0",
        "Date": "16/08/2024",
        "Time": "20:00",
        "HomeTeam": "Man United",
        "AwayTeam": "Fulham",
        "FTHG": 1,
        "FTAG": 0,
        "FTR": "H",
        "HTHG": 1,
        "HTAG": 0,
        "HTR": "H",
        "Referee": "A Taylor",
        "HS": 12,
        "AS": 9,
        "HST": 4,
        "AST": 2,
        "HF": 10,
        "AF": 13,
        "HC": 5,
        "AC": 4,
        "HY": 2,
        "AY": 1,
        "HR": 0,
        "AR": 0,
        "B365H": 1.75,
        "B365D": 3.80,
        "B365A": 4.50,
    }
    base.update(overrides)
    return base


def test_parses_modern_row() -> None:
    row = FootballDataRow.model_validate(_modern_row())
    assert row.div == "E0"
    assert row.match_date == date(2024, 8, 16)
    assert row.match_time == time(20, 0)
    assert row.home_team == "Man United"
    assert row.away_team == "Fulham"
    assert row.fthg == 1
    assert row.ftag == 0
    assert row.ftr == "H"
    assert row.b365h == pytest.approx(1.75)


def test_parses_two_digit_year() -> None:
    """Old-season CSVs use dd/mm/yy. %y pivots at 69/70."""
    row = FootballDataRow.model_validate(_modern_row(Date="15/08/15"))
    assert row.match_date == date(2015, 8, 15)

    # Pivot: 99 -> 1999, not 2099
    old = FootballDataRow.model_validate(_modern_row(Date="19/08/99"))
    assert old.match_date == date(1999, 8, 19)


def test_nullable_stats_empty_string() -> None:
    """Empty-string cells on optional columns become None, not a parse error."""
    row = FootballDataRow.model_validate(_modern_row(HST="", HC="", AS="NA"))
    assert row.hst is None
    assert row.hc is None
    assert row.as_ is None


def test_unknown_column_flows_to_extras() -> None:
    """Columns not declared on the model land in __pydantic_extra__.

    Uses ``1XBH`` (1xBet 1X2 home opening) — a deferred column per the migration
    002 "promote on second appearance" rule, so it remains genuinely unknown to
    the registry until at least migration 003.
    """
    row = FootballDataRow.model_validate(_modern_row(Foo="bar", **{"1XBH": 1.72}))
    assert row.__pydantic_extra__ == {"Foo": "bar", "1XBH": 1.72}


def test_rejects_malformed_odds() -> None:
    """Non-numeric value in a numeric column must fail validation, not coerce."""
    with pytest.raises(ValidationError):
        FootballDataRow.model_validate(_modern_row(B365H="abc"))


def test_missing_required_raises() -> None:
    """Absent required field (FTHG) fails validation."""
    row_dict = _modern_row()
    del row_dict["FTHG"]
    with pytest.raises(ValidationError):
        FootballDataRow.model_validate(row_dict)


def test_empty_required_raises() -> None:
    """Empty-string FTHG is nullified then rejected because field is non-optional int."""
    with pytest.raises(ValidationError):
        FootballDataRow.model_validate(_modern_row(FTHG=""))


def test_time_column_absent_defaults_to_none() -> None:
    """Old seasons have no Time column; model defaults to None without error."""
    row_dict = _modern_row()
    del row_dict["Time"]
    row = FootballDataRow.model_validate(row_dict)
    assert row.match_time is None
