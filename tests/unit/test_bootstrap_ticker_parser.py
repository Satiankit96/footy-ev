"""Unit tests for _parse_ticker — Kalshi event ticker decoder.

Format: KXEPLTOTAL-{YY}{MON}{DD}{AWAY3}{HOME3}
  yy   2-digit year (2000-offset)
  mon  3-letter month upper, JAN..DEC
  dd   2-digit day
  away 3-letter away team code
  home 3-letter home team code
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from bootstrap_kalshi_aliases import _parse_ticker  # type: ignore[import-not-found] # noqa: E402


def test_valid_ticker_parses_to_date_and_codes() -> None:
    parts = _parse_ticker("KXEPLTOTAL-26MAY24WHULEE")
    assert parts is not None
    assert parts.kickoff_date == date(2026, 5, 24)
    assert parts.away_code == "WHU"
    assert parts.home_code == "LEE"


def test_malformed_ticker_returns_none() -> None:
    assert _parse_ticker("INVALID") is None
    assert _parse_ticker("KXEPLTOTAL-26MAY24WHULEE-extra") is None
    assert _parse_ticker("KXNBA-26MAY24WHULEE") is None


def test_all_twelve_months_parse() -> None:
    months = [
        ("JAN", 1),
        ("FEB", 2),
        ("MAR", 3),
        ("APR", 4),
        ("MAY", 5),
        ("JUN", 6),
        ("JUL", 7),
        ("AUG", 8),
        ("SEP", 9),
        ("OCT", 10),
        ("NOV", 11),
        ("DEC", 12),
    ]
    for mon_str, mon_num in months:
        parts = _parse_ticker(f"KXEPLTOTAL-26{mon_str}15ARSLIV")
        assert parts is not None, f"month {mon_str} should parse"
        assert parts.kickoff_date.month == mon_num


def test_year_edge_cases() -> None:
    # yy=00 → 2000
    parts = _parse_ticker("KXEPLTOTAL-00JAN01ARSLIV")
    assert parts is not None and parts.kickoff_date.year == 2000
    # yy=99 → 2099
    parts = _parse_ticker("KXEPLTOTAL-99DEC31ARSLIV")
    assert parts is not None and parts.kickoff_date.year == 2099


def test_invalid_month_returns_none() -> None:
    # ZZZ is not a recognized month
    assert _parse_ticker("KXEPLTOTAL-26ZZZ24WHULEE") is None
    # Lowercase rejected by regex (codes are uppercase only)
    assert _parse_ticker("KXEPLTOTAL-26may24WHULEE") is None


def test_invalid_day_returns_none() -> None:
    # 30 February doesn't exist
    assert _parse_ticker("KXEPLTOTAL-26FEB30WHULEE") is None
    # 32 May doesn't exist
    assert _parse_ticker("KXEPLTOTAL-26MAY32WHULEE") is None
    # 00 is not a valid day
    assert _parse_ticker("KXEPLTOTAL-26MAY00WHULEE") is None
