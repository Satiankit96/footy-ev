"""Pydantic model for a single football-data.co.uk match row.

The model uses source-column aliases (``FTHG``, ``HomeTeam``, ``B365>2.5``, ...) so it
can validate directly against dicts produced by ``polars.read_csv``. Unknown source
columns survive on ``__pydantic_extra__`` thanks to ``model_config extra="allow"``
and are later dumped into the ``extras`` MAP column by ``loader.py``.

Date parsing handles both modern (``dd/mm/yyyy``) and old-season (``dd/mm/yy``)
formats; two-digit years are pivoted by ``%y`` at 69/70 per Python stdlib convention.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NULLY_STRINGS = {"", "NA", "N/A", "NULL"}


class FootballDataRow(BaseModel):
    """One parsed row from a football-data.co.uk CSV."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # --- Core match ---
    div: str = Field(alias="Div")
    match_date: date = Field(alias="Date")
    match_time: time | None = Field(default=None, alias="Time")
    home_team: str = Field(alias="HomeTeam")
    away_team: str = Field(alias="AwayTeam")
    fthg: int = Field(alias="FTHG")
    ftag: int = Field(alias="FTAG")
    ftr: str = Field(alias="FTR")
    hthg: int | None = Field(default=None, alias="HTHG")
    htag: int | None = Field(default=None, alias="HTAG")
    htr: str | None = Field(default=None, alias="HTR")
    referee: str | None = Field(default=None, alias="Referee")

    # --- Match stats ---
    hs: int | None = Field(default=None, alias="HS")
    as_: int | None = Field(default=None, alias="AS")
    hst: int | None = Field(default=None, alias="HST")
    ast: int | None = Field(default=None, alias="AST")
    hf: int | None = Field(default=None, alias="HF")
    af: int | None = Field(default=None, alias="AF")
    hc: int | None = Field(default=None, alias="HC")
    ac: int | None = Field(default=None, alias="AC")
    hy: int | None = Field(default=None, alias="HY")
    ay: int | None = Field(default=None, alias="AY")
    hr: int | None = Field(default=None, alias="HR")
    ar: int | None = Field(default=None, alias="AR")

    # --- 1X2 decimal odds ---
    b365h: float | None = Field(default=None, alias="B365H")
    b365d: float | None = Field(default=None, alias="B365D")
    b365a: float | None = Field(default=None, alias="B365A")
    bwh: float | None = Field(default=None, alias="BWH")
    bwd: float | None = Field(default=None, alias="BWD")
    bwa: float | None = Field(default=None, alias="BWA")
    iwh: float | None = Field(default=None, alias="IWH")
    iwd: float | None = Field(default=None, alias="IWD")
    iwa: float | None = Field(default=None, alias="IWA")
    psh: float | None = Field(default=None, alias="PSH")
    psd: float | None = Field(default=None, alias="PSD")
    psa: float | None = Field(default=None, alias="PSA")
    whh: float | None = Field(default=None, alias="WHH")
    whd: float | None = Field(default=None, alias="WHD")
    wha: float | None = Field(default=None, alias="WHA")
    vch: float | None = Field(default=None, alias="VCH")
    vcd: float | None = Field(default=None, alias="VCD")
    vca: float | None = Field(default=None, alias="VCA")
    maxh: float | None = Field(default=None, alias="MaxH")
    maxd: float | None = Field(default=None, alias="MaxD")
    maxa: float | None = Field(default=None, alias="MaxA")
    avgh: float | None = Field(default=None, alias="AvgH")
    avgd: float | None = Field(default=None, alias="AvgD")
    avga: float | None = Field(default=None, alias="AvgA")
    bfeh: float | None = Field(default=None, alias="BFEH")
    bfed: float | None = Field(default=None, alias="BFED")
    bfea: float | None = Field(default=None, alias="BFEA")

    # --- Over/Under 2.5 goals ---
    b365_over_25: float | None = Field(default=None, alias="B365>2.5")
    b365_under_25: float | None = Field(default=None, alias="B365<2.5")
    p_over_25: float | None = Field(default=None, alias="P>2.5")
    p_under_25: float | None = Field(default=None, alias="P<2.5")
    max_over_25: float | None = Field(default=None, alias="Max>2.5")
    max_under_25: float | None = Field(default=None, alias="Max<2.5")
    avg_over_25: float | None = Field(default=None, alias="Avg>2.5")
    avg_under_25: float | None = Field(default=None, alias="Avg<2.5")

    # --- Asian handicap ---
    ah_line: float | None = Field(default=None, alias="AHh")
    b365_ah_home: float | None = Field(default=None, alias="B365AHH")
    b365_ah_away: float | None = Field(default=None, alias="B365AHA")
    p_ah_home: float | None = Field(default=None, alias="PAHH")
    p_ah_away: float | None = Field(default=None, alias="PAHA")

    @model_validator(mode="before")
    @classmethod
    def _nullify_empty_strings(cls, data: Any) -> Any:
        """Turn ``""`` / ``"NA"`` / ``"N/A"`` / ``"NULL"`` into ``None`` across all inputs.

        This runs before field-level validation, so optional fields of any type
        (``int | None``, ``float | None``, ``str | None``, ``time | None``) uniformly
        treat these null-ish strings as missing. Required fields still fail loudly —
        passing ``None`` into ``fthg: int`` raises ``ValidationError``, which is correct.
        """
        if not isinstance(data, dict):
            return data
        out: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str) and v.strip() in _NULLY_STRINGS:
                out[k] = None
            else:
                out[k] = v
        return out

    @field_validator("match_date", mode="before")
    @classmethod
    def _parse_date_cell(cls, v: Any) -> Any:
        if v is None or isinstance(v, date):
            return v
        if isinstance(v, str):
            s = v.strip()
            for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    return datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"match_date: unrecognized format {s!r}")
        raise TypeError(f"match_date: expected str or date, got {type(v).__name__}")

    @field_validator("match_time", mode="before")
    @classmethod
    def _parse_time_cell(cls, v: Any) -> Any:
        if v is None or isinstance(v, time):
            return v
        if isinstance(v, str):
            s = v.strip()
            for fmt in ("%H:%M", "%H:%M:%S"):
                try:
                    return datetime.strptime(s, fmt).time()
                except ValueError:
                    continue
            raise ValueError(f"match_time: unrecognized format {s!r}")
        raise TypeError(f"match_time: expected str or time, got {type(v).__name__}")


if __name__ == "__main__":
    row = FootballDataRow.model_validate(
        {
            "Div": "E0",
            "Date": "16/08/2024",
            "Time": "20:00",
            "HomeTeam": "Man United",
            "AwayTeam": "Fulham",
            "FTHG": 1,
            "FTAG": 0,
            "FTR": "H",
            "B365H": 1.75,
            "Foo": "unknown-column-value",
        }
    )
    print(f"parsed: {row.home_team} vs {row.away_team} on {row.match_date}")
    print(f"extras: {row.__pydantic_extra__}")
