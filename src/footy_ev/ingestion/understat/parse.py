"""Parse Understat league/season AJAX JSON payloads into validated match records.

Source payload shape (from ``GET /getLeagueData/<LEAGUE>/<YEAR>``):

    {
        "dates":   [ <match dict>, ... ],   # what we consume
        "teams":   { ... },                  # informational; unused here
        "players": [ ... ]                   # informational; unused here
    }

Each match dict::

    {
        "id":       "22275",
        "isResult": true,
        "h":        {"id": "92", "title": "Burnley", "short_title": "BUR"},
        "a":        {"id": "88", "title": "Manchester City", "short_title": "MCI"},
        "goals":    {"h": "0",        "a": "3"},          # null on unplayed
        "xG":       {"h": "0.311032", "a": "2.40074"},    # null on unplayed
        "datetime": "2023-08-11 19:00:00",                 # naive league-local
        "forecast": {"w": "0.0177", "d": "0.0854", "l": "0.8969"}   # ABSENT on unplayed
    }

Module layout (per R6):
    1. Pydantic model (top)
    2. Pure helpers — TZ conversion, flatten (middle)
    3. Public ``extract_matches`` / ``parse_payload`` entry points (bottom)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, NaiveDatetime, StrictBool

from footy_ev.ingestion.understat import UnderstatParseError


# --------------------------------------------------------------------------- #
# Pydantic model
# --------------------------------------------------------------------------- #
class UnderstatMatchRecord(BaseModel):
    """One validated match parsed from an Understat ``dates`` entry.

    Mirrors the FootballDataRow pattern: ``extra="allow"`` lets unknown
    sibling keys (anything beyond the documented set ``id``, ``isResult``,
    ``h``, ``a``, ``goals``, ``xG``, ``datetime``, ``forecast``) survive on
    ``__pydantic_extra__`` for the loader to dump into the ``extras`` MAP and
    log to ``schema_drift_log``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Stable identifiers
    understat_match_id: str
    understat_home_id: str
    understat_away_id: str

    # Raw team strings (NOT entity-resolved; resolved via team_aliases at query time)
    home_team_raw: str
    away_team_raw: str

    # Match facts. ``kickoff_local`` is naive (league-local civil time as scraped);
    # ``kickoff_utc`` is canonical for downstream queries. ``StrictBool`` on
    # ``is_result`` pins the JSON-native-bool expectation — if Understat ever
    # emits ``"true"``/``"false"`` strings, validation fails loudly instead of
    # silently coercing.
    kickoff_local: NaiveDatetime
    kickoff_utc: AwareDatetime
    is_result: StrictBool
    home_goals: int | None = None
    away_goals: int | None = None
    home_xg: float | None = None
    away_xg: float | None = None

    # forecast.{w,d,l}: Understat's own win/draw/loss attribution.
    # CRITICAL: empirically populated ONLY on played matches (key absent
    # on unplayed). This means it is a POST-MATCH attribution computed
    # from realized xG, not a pre-match prediction. Using it as a feature
    # in any pre-kickoff model is data leakage. Stored for completeness
    # and potential post-match analysis only. See LEARNING_LOG.md
    # Episode 11 for the discovery and reasoning.
    forecast_home_pct: float | None = None
    forecast_draw_pct: float | None = None
    forecast_away_pct: float | None = None


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
MIN_EXPECTED_MATCHES_PER_SEASON: Final[int] = 50
"""Sanity floor for parsed match count. Set to 50 to safely cover early-season
in-progress fixtures while catching 'AJAX endpoint shape changed' or
'Understat changed the schema' failures. A full top-5 league season is
~340-380 matches; even a freshly opened season has 50+ scheduled fixtures
visible by August."""

LEAGUE_TZ: Final[dict[str, str]] = {
    "EPL": "Europe/London",
    # Other leagues land in a later step. Adding them here without
    # corresponding tests/fixtures would be premature.
}

# Source-payload sibling keys that flatten into UnderstatMatchRecord fields.
# Anything else at the top of a match dict flows to ``extras`` via Pydantic's
# ``extra="allow"``.
_KNOWN_MATCH_KEYS: Final[frozenset[str]] = frozenset(
    {"id", "isResult", "h", "a", "goals", "xG", "datetime", "forecast"}
)

_KICKOFF_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


def convert_kickoff(local_ts: datetime, league: str) -> datetime:
    """Convert a naive league-local timestamp to UTC.

    Args:
        local_ts: Naive ``datetime`` as scraped from Understat's ``datetime``
            field. Must be in the league's local civil time.
        league: Canonical league code; must be a key in ``LEAGUE_TZ``.

    Returns:
        Timezone-aware UTC ``datetime``.

    Raises:
        TypeError: If ``local_ts`` is timezone-aware (callers must pass naive).
        ValueError: If ``league`` is not in ``LEAGUE_TZ``.
    """
    if local_ts.tzinfo is not None:
        raise TypeError(f"convert_kickoff: local_ts must be naive, got tzinfo={local_ts.tzinfo}")
    if league not in LEAGUE_TZ:
        raise ValueError(
            f"convert_kickoff: league {league!r} not in LEAGUE_TZ; known: {sorted(LEAGUE_TZ)}"
        )
    aware_local = local_ts.replace(tzinfo=ZoneInfo(LEAGUE_TZ[league]))
    return aware_local.astimezone(UTC)


def _flatten_match(raw: dict[str, Any], league: str) -> dict[str, Any]:
    """Flatten one source match dict into model-shaped kwargs.

    Unknown sibling keys (anything in ``raw`` not in ``_KNOWN_MATCH_KEYS``) are
    preserved verbatim so Pydantic's ``extra="allow"`` routes them to
    ``__pydantic_extra__``.

    Raises:
        UnderstatParseError: If ``raw["datetime"]`` is missing, non-string, or
            doesn't match the expected ``YYYY-MM-DD HH:MM:SS`` format.
    """
    h = raw.get("h") or {}
    a = raw.get("a") or {}
    goals = raw.get("goals") or {}
    xg = raw.get("xG") or {}
    forecast = raw.get("forecast") or {}

    dt_str = raw.get("datetime")
    if not isinstance(dt_str, str):
        raise UnderstatParseError(
            f"match {raw.get('id')!r}: 'datetime' must be a string, got {type(dt_str).__name__}"
        )
    try:
        kickoff_local = datetime.strptime(dt_str, _KICKOFF_FORMAT)
    except ValueError as e:
        raise UnderstatParseError(
            f"match {raw.get('id')!r}: unrecognized datetime format {dt_str!r}: {e}"
        ) from e
    kickoff_utc = convert_kickoff(kickoff_local, league)

    flat: dict[str, Any] = {
        "understat_match_id": raw.get("id"),
        "understat_home_id": h.get("id"),
        "understat_away_id": a.get("id"),
        "home_team_raw": h.get("title"),
        "away_team_raw": a.get("title"),
        "kickoff_local": kickoff_local,
        "kickoff_utc": kickoff_utc,
        "is_result": raw.get("isResult"),
        "home_goals": goals.get("h"),
        "away_goals": goals.get("a"),
        "home_xg": xg.get("h"),
        "away_xg": xg.get("a"),
        "forecast_home_pct": forecast.get("w"),
        "forecast_draw_pct": forecast.get("d"),
        "forecast_away_pct": forecast.get("l"),
    }
    for k, v in raw.items():
        if k not in _KNOWN_MATCH_KEYS:
            flat[k] = v
    return flat


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def extract_matches(
    payload: Any,
    *,
    season: str,
    league: str,
) -> list[UnderstatMatchRecord]:
    """Extract and validate all match records from an Understat AJAX JSON payload.

    Args:
        payload: Already-decoded JSON object from ``GET /getLeagueData/...``.
            Expected to be a dict with at minimum a ``"dates"`` key whose value
            is a list of match dicts.
        season: Human season string like ``"2024-2025"`` (used in error messages
            and downstream loader; not derived from the payload).
        league: Canonical league code; controls the TZ used for kickoff conversion.

    Returns:
        Validated match records, one per element of ``payload["dates"]``. Order
        matches the source JSON.

    Raises:
        UnderstatParseError: If the payload isn't a dict, lacks a list-valued
            ``dates`` key, has fewer than ``MIN_EXPECTED_MATCHES_PER_SEASON``
            matches, or any match dict fails Pydantic validation.
    """
    if not isinstance(payload, dict):
        raise UnderstatParseError(
            f"payload must be a dict (top-level JSON object), got "
            f"{type(payload).__name__} for {league} {season}"
        )
    dates = payload.get("dates")
    if not isinstance(dates, list):
        raise UnderstatParseError(
            f"payload['dates'] must be a list, got {type(dates).__name__} for {league} {season}"
        )
    if len(dates) < MIN_EXPECTED_MATCHES_PER_SEASON:
        raise UnderstatParseError(
            f"payload['dates'] has only {len(dates)} entries for {league} {season}, "
            f"expected >= {MIN_EXPECTED_MATCHES_PER_SEASON}. Likely the AJAX "
            f"endpoint shape changed; verify against understatapi's current "
            f"implementation before relaxing this floor."
        )

    return [UnderstatMatchRecord.model_validate(_flatten_match(m, league)) for m in dates]


def parse_payload(
    text: str | bytes,
    *,
    season: str,
    league: str,
) -> list[UnderstatMatchRecord]:
    """Decode the raw AJAX response text and extract matches in one call.

    Convenience wrapper for ``json.loads(text); extract_matches(...)`` that
    funnels ``json.JSONDecodeError`` into ``UnderstatParseError`` for a uniform
    error type at the parse-layer boundary.

    Raises:
        UnderstatParseError: On JSON decode failure or any failure raised by
            ``extract_matches``.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise UnderstatParseError(f"JSON decode failed for {league} {season}: {e}") from e
    return extract_matches(payload, season=season, league=league)


if __name__ == "__main__":
    sample_match = {
        "id": "22275",
        "isResult": True,
        "h": {"id": "92", "title": "Burnley", "short_title": "BUR"},
        "a": {"id": "88", "title": "Manchester City", "short_title": "MCI"},
        "goals": {"h": "0", "a": "3"},
        "xG": {"h": "0.311032", "a": "2.40074"},
        "datetime": "2023-08-11 19:00:00",
        "forecast": {"w": "0.0177", "d": "0.0854", "l": "0.8969"},
    }
    payload = {"dates": [sample_match] * 50, "teams": {}, "players": []}
    matches = extract_matches(payload, season="2023-2024", league="EPL")
    print(f"parsed {len(matches)} matches; sample: {matches[0]!r}")
