"""Fetch football-data.co.uk season CSVs.

One HTTP GET per season, written verbatim to
``data/raw/football_data/{source_code}/{season_code}.csv`` (immutable source-of-truth
archive per CLAUDE.md). Re-invocation with an existing cache file is a no-op unless
``refresh=True``.

Retry policy: exponential backoff on transient network errors and 5xx responses only.
4xx errors (including 404 for seasons that don't exist yet) fail fast — no point
retrying a permanent missing resource.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from footy_ev import __version__

if TYPE_CHECKING:
    from pathlib import Path

LEAGUE_TO_SOURCE: Final[dict[str, str]] = {
    "EPL": "E0",
    "LaLiga": "SP1",
    "SerieA": "I1",
    "Bundesliga": "D1",
    "Ligue1": "F1",
}

_USER_AGENT: Final[str] = f"footy-ev/{__version__} (+https://github.com/Satiankit96/footy-ev)"
_TIMEOUT_SECS: Final[float] = 30.0
_URL_BASE: Final[str] = "https://www.football-data.co.uk/mmz4281"


def season_to_code(season: str) -> str:
    """Convert a season string like ``"2024-2025"`` to the URL code ``"2425"``.

    Raises:
        ValueError: If ``season`` is not ``YYYY-YYYY`` with consecutive years.
    """
    if len(season) != 9 or season[4] != "-":
        raise ValueError(f"expected 'YYYY-YYYY', got {season!r}")
    y1, y2 = season[:4], season[5:]
    if not (y1.isdigit() and y2.isdigit()):
        raise ValueError(f"expected numeric years, got {season!r}")
    if int(y2) != int(y1) + 1:
        raise ValueError(f"season years must be consecutive, got {season!r}")
    return y1[-2:] + y2[-2:]


def league_to_source_code(league: str) -> str:
    """Map a canonical league code (e.g. ``"EPL"``) to its football-data.co.uk file code."""
    if league not in LEAGUE_TO_SOURCE:
        raise ValueError(f"unknown league {league!r}; expected one of {sorted(LEAGUE_TO_SOURCE)}")
    return LEAGUE_TO_SOURCE[league]


def build_url(league: str, season: str) -> str:
    """Build the CSV URL for one (league, season)."""
    return f"{_URL_BASE}/{season_to_code(season)}/{league_to_source_code(league)}.csv"


def cache_path(raw_dir: Path, league: str, season: str) -> Path:
    """Where the season's raw CSV is cached on disk."""
    return raw_dir / league_to_source_code(league) / f"{season_to_code(season)}.csv"


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return int(exc.response.status_code) >= 500
    return isinstance(exc, httpx.RequestError)


@retry(  # type: ignore[misc]
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)
def _download_bytes(url: str) -> bytes:
    with httpx.Client(
        timeout=_TIMEOUT_SECS,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content  # type: ignore[no-any-return]


def fetch_season(
    league: str,
    season: str,
    raw_dir: Path,
    *,
    refresh: bool = False,
) -> Path:
    """Fetch one season's CSV and write it to the cache directory.

    Idempotent: if the cache file already exists and ``refresh`` is False, returns
    immediately without a network call.

    Args:
        league: Canonical league code (e.g. ``"EPL"``).
        season: Human season string like ``"2024-2025"``.
        raw_dir: Root directory under which ``{source_code}/{season_code}.csv`` lives.
        refresh: If True, re-download even when the cache file exists.

    Returns:
        Path to the cached CSV file.
    """
    path = cache_path(raw_dir, league, season)
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _download_bytes(build_url(league, season))
    path.write_bytes(content)
    return path


if __name__ == "__main__":
    print("season '2024-2025' ->", season_to_code("2024-2025"))
    print("url:", build_url("EPL", "2024-2025"))
