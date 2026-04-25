"""Unit tests for football_data/source.py (pure logic + idempotent caching)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

from footy_ev.ingestion.football_data import source as src_mod

if TYPE_CHECKING:
    from pathlib import Path


def test_season_to_code_modern() -> None:
    assert src_mod.season_to_code("2024-2025") == "2425"


def test_season_to_code_turn_of_millennium() -> None:
    assert src_mod.season_to_code("1999-2000") == "9900"


def test_season_to_code_rejects_nonconsecutive_years() -> None:
    with pytest.raises(ValueError):
        src_mod.season_to_code("2024-2026")


def test_season_to_code_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        src_mod.season_to_code("24-25")


def test_league_to_source_code_known() -> None:
    assert src_mod.league_to_source_code("EPL") == "E0"
    assert src_mod.league_to_source_code("Bundesliga") == "D1"


def test_league_to_source_code_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        src_mod.league_to_source_code("MLS")


def test_build_url() -> None:
    url = src_mod.build_url("EPL", "2024-2025")
    assert url == "https://www.football-data.co.uk/mmz4281/2425/E0.csv"


def test_cache_path(tmp_path: Path) -> None:
    p = src_mod.cache_path(tmp_path, "EPL", "2024-2025")
    assert p == tmp_path / "E0" / "2425.csv"


def test_fetch_season_returns_cached_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the cache file exists and refresh=False, do not touch the network."""

    def _boom(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("httpx.Client should not be instantiated for cached reads")

    monkeypatch.setattr(httpx, "Client", _boom)

    cached = src_mod.cache_path(tmp_path, "EPL", "2024-2025")
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"Div,Date\nE0,16/08/2024\n")

    path = src_mod.fetch_season("EPL", "2024-2025", raw_dir=tmp_path, refresh=False)
    assert path == cached
    assert path.read_bytes() == b"Div,Date\nE0,16/08/2024\n"
