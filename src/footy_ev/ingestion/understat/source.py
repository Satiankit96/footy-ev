"""Fetch Understat league/season AJAX JSON payloads.

# Endpoint discovered via understatapi v0.7.1 source inspection
# (commit 2025-12-17: "Fix: use AJAX endpoints instead of HTML parsing").
# Understat deprecated inline-JSON in league/team pages sometime in 2025;
# this AJAX endpoint is public-by-convention but undocumented. If it
# breaks, check understatapi's GitHub for the current pattern before
# reverse-engineering ourselves.

One HTTP GET per (league, season) to
``https://understat.com/getLeagueData/<UNDERSTAT_CODE>/<YEAR>``, written verbatim
(after pretty-printing for diff readability) to
``data/raw/understat/{league}/{season}.json`` plus a ``.sha256`` sidecar for
tamper detection. Re-invocation with an existing cache file is a no-op unless
``refresh=True``.

Required header: ``X-Requested-With: XMLHttpRequest``. No cookies, no auth.

Polite scraping: ≥2s between requests (CLAUDE.md hard rule). Caller is
responsible for rate-limiting across multiple seasons; this module is a
single-shot fetcher.

Retry policy: exponential backoff on transient network errors and 5xx responses.
4xx errors fail fast — Understat 404s on seasons before 2014-15, and we want
that to surface as a permanent error, not a retry-storm.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from footy_ev import __version__
from footy_ev.ingestion.understat import UnderstatFetchError

LEAGUE_TO_UNDERSTAT_CODE: Final[dict[str, str]] = {
    "EPL": "EPL",
    "LaLiga": "La_liga",
    "SerieA": "Serie_A",
    "Bundesliga": "Bundesliga",
    "Ligue1": "Ligue_1",
}

UNDERSTAT_RATE_LIMIT_SECS: Final[float] = 2.0

_USER_AGENT: Final[str] = f"footy-ev/{__version__} (+https://github.com/Satiankit96/footy-ev)"
_TIMEOUT_SECS: Final[float] = 30.0
_URL_BASE: Final[str] = "https://understat.com"
_AJAX_HEADERS: Final[dict[str, str]] = {"X-Requested-With": "XMLHttpRequest"}


def season_to_year_code(season: str) -> str:
    """Convert ``"2024-2025"`` to ``"2024"`` (Understat URL year code).

    Understat indexes a season by its starting year — the EPL 2024-25 season
    lives at ``/getLeagueData/EPL/2024``.

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
    return y1


def league_to_understat_code(league: str) -> str:
    """Map a canonical league code (e.g. ``"LaLiga"``) to its Understat URL code (``"La_liga"``)."""
    if league not in LEAGUE_TO_UNDERSTAT_CODE:
        raise ValueError(
            f"unknown league {league!r}; expected one of {sorted(LEAGUE_TO_UNDERSTAT_CODE)}"
        )
    return LEAGUE_TO_UNDERSTAT_CODE[league]


def build_url(league: str, season: str) -> str:
    """Build the AJAX getLeagueData URL for one (league, season)."""
    return (
        f"{_URL_BASE}/getLeagueData/"
        f"{league_to_understat_code(league)}/{season_to_year_code(season)}"
    )


def cache_path(raw_dir: Path, league: str, season: str) -> Path:
    """Where the season's raw JSON is cached on disk."""
    return raw_dir / league / f"{season}.json"


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
def _download(url: str) -> bytes:
    headers = {"User-Agent": _USER_AGENT, **_AJAX_HEADERS}
    with httpx.Client(
        timeout=_TIMEOUT_SECS,
        follow_redirects=True,
        headers=headers,
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
    """Fetch one season's Understat AJAX JSON and write it to the cache directory.

    Idempotent: if the cache file already exists and ``refresh`` is False, returns
    immediately without a network call. Writes a ``<file>.sha256`` sidecar
    alongside the JSON for tamper detection. The cached file is the AJAX response
    body re-serialized with ``sort_keys=True, indent=2`` for diffability.

    Args:
        league: Canonical league code (e.g. ``"EPL"``).
        season: Human season string like ``"2024-2025"``.
        raw_dir: Root directory under which ``{league}/{season}.json`` lives.
        refresh: If True, re-download even when the cache file exists.

    Returns:
        Path to the cached JSON file.

    Raises:
        UnderstatFetchError: If the fetch fails permanently (4xx), retries are
            exhausted on transient errors, or the upstream returns non-JSON.
    """
    path = cache_path(raw_dir, league, season)
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        raw = _download(build_url(league, season))
    except httpx.HTTPStatusError as e:
        raise UnderstatFetchError(
            f"HTTP {e.response.status_code} for {league} {season}: {e.request.url}"
        ) from e
    except httpx.RequestError as e:
        raise UnderstatFetchError(
            f"network error for {league} {season}: {e.__class__.__name__}: {e}"
        ) from e

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UnderstatFetchError(
            f"upstream returned non-JSON for {league} {season}: {e}"
        ) from e

    pretty = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
    path.write_bytes(pretty)

    sha = hashlib.sha256(pretty).hexdigest()
    sha_path = path.parent / (path.name + ".sha256")
    sha_path.write_text(sha + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print("season '2024-2025' ->", season_to_year_code("2024-2025"))
    print("url:", build_url("EPL", "2024-2025"))
