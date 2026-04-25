"""Unit tests for the ingestion CLI's pure helpers (no network, no DB)."""

from __future__ import annotations

from datetime import date

import pytest

from footy_ev.ingestion.cli import current_season, season_range


def test_current_season_august_onward() -> None:
    assert current_season(date(2024, 8, 1)) == "2024-2025"
    assert current_season(date(2024, 12, 31)) == "2024-2025"


def test_current_season_pre_august() -> None:
    assert current_season(date(2025, 1, 15)) == "2024-2025"
    assert current_season(date(2025, 7, 31)) == "2024-2025"


def test_season_range_one_season() -> None:
    assert season_range("2024-2025", "2024-2025") == ["2024-2025"]


def test_season_range_multiple() -> None:
    out = season_range("2022-2023", "2024-2025")
    assert out == ["2022-2023", "2023-2024", "2024-2025"]


def test_season_range_full_backfill() -> None:
    out = season_range("2000-2001", "2024-2025")
    assert len(out) == 25
    assert out[0] == "2000-2001"
    assert out[-1] == "2024-2025"


def test_season_range_rejects_reverse() -> None:
    with pytest.raises(ValueError):
        season_range("2024-2025", "2022-2023")
