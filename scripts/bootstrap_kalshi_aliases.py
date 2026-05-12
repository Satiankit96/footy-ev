# ruff: noqa: E402
"""One-off bootstrap script: populate kalshi_event_aliases from fixture file or live API.

Resolution flow per Kalshi event:
  1. _parse_ticker: extract (kickoff_date, away_code, home_code) from event_ticker.
     This is the PRIMARY signal — Kalshi tickers encode teams + date deterministically.
  2. _resolve_team_by_code: look up team_id via team_aliases(source='kalshi_code').
  3. _parse_teams_from_title: fallback used when (1) or (2) fails. Handles both
     "X at Y: Total Goals" (US convention: X=away, Y=home) and "X vs Y: Totals"
     (X=home, Y=away). Strips ": Total Goals", ": Totals", " - Total Goals",
     " - Totals", " Total Goals", " Totals" case-insensitively.
  4. _find_fixture_id: query v_fixtures_epl on (home, away, date ± 1d) where
     status != 'final'. Multiple matches → closest date wins, WARN on ambiguity.
  5. If no fixture match AND --create-fixtures (default): INSERT a synthetic
     row into synthetic_fixtures (gated to kickoff_date in [now-24h, now+14d]).
     Then resolve aliases against the synthetic fixture_id.

Modes:
  --from-fixture PATH   Read a JSON fixture file (offline, no auth).
  --live                Call Kalshi list_events() (requires KALSHI_API_KEY_ID).

Usage:
    python scripts/bootstrap_kalshi_aliases.py --from-fixture tests/fixtures/kalshi_events_sample.json
    python scripts/bootstrap_kalshi_aliases.py --live
    python scripts/bootstrap_kalshi_aliases.py --live --no-create-fixtures
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

import duckdb
from rapidfuzz import fuzz, process

from footy_ev.db import apply_migrations, apply_views

DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "warehouse" / "footy_ev.duckdb"
DEFAULT_THRESHOLD = 75
FUZZY_ACCEPT_THRESHOLD = 85

# Ticker format: KXEPLTOTAL-{YY}{MON}{DD}{AWAY3}{HOME3}
# Example:      KXEPLTOTAL-26MAY24WHULEE = WHU(away) at LEE(home) on 2026-05-24
_TICKER_PATTERN = re.compile(
    r"^KXEPLTOTAL-"
    r"(?P<yy>\d{2})"
    r"(?P<mon>[A-Z]{3})"
    r"(?P<dd>\d{2})"
    r"(?P<away>[A-Z]{3})"
    r"(?P<home>[A-Z]{3})$"
)
_MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

# Title suffixes seen on demo (2026-05-12 capture): ": Total Goals", ": Totals",
# and dash-separated variants. Matched case-insensitively at end of title.
_TITLE_SUFFIX_PATTERN = re.compile(
    r"(?:\s*[:\-]\s*)?\s*total(?:s)?(?:\s+goals)?\s*$",
    re.IGNORECASE,
)

# Two formats observed: "X at Y" (US: X=away, Y=home) and "X vs Y" (X=home, Y=away).
_AT_PATTERN = re.compile(r"\s+at\s+", re.IGNORECASE)
_VS_PATTERN = re.compile(r"\s+vs\s+", re.IGNORECASE)

# Synthetic fixture window: kickoff_date must be in [today - 1d, today + 14d].
_SYNTHETIC_PAST_TOLERANCE = timedelta(days=1)
_SYNTHETIC_FUTURE_HORIZON = timedelta(days=14)


@dataclass(frozen=True)
class KalshiTickerParts:
    kickoff_date: date
    away_code: str
    home_code: str


def _parse_ticker(ticker: str) -> KalshiTickerParts | None:
    """Parse a KXEPLTOTAL ticker into (kickoff_date, away_code, home_code).

    Returns None if the ticker does not match the expected format or contains
    an invalid month/day.
    """
    m = _TICKER_PATTERN.match(ticker)
    if not m:
        return None
    mon_str = m.group("mon")
    if mon_str not in _MONTH_MAP:
        return None
    year = 2000 + int(m.group("yy"))
    month = _MONTH_MAP[mon_str]
    try:
        kickoff_date = date(year, month, int(m.group("dd")))
    except ValueError:
        return None
    return KalshiTickerParts(
        kickoff_date=kickoff_date,
        away_code=m.group("away"),
        home_code=m.group("home"),
    )


def _resolve_team_by_code(con: duckdb.DuckDBPyConnection, code: str) -> str | None:
    """Look up team_id by Kalshi 3-letter code via team_aliases."""
    row = con.execute(
        "SELECT team_id FROM team_aliases WHERE source = 'kalshi_code' AND raw_name = ?",
        [code],
    ).fetchone()
    return str(row[0]) if row else None


def _strip_title_suffix(title: str) -> str:
    """Remove ': Total Goals', ': Totals', ' - Total Goals', etc. case-insensitively."""
    return _TITLE_SUFFIX_PATTERN.sub("", title).strip()


def _parse_teams_from_title(title: str) -> tuple[str, str] | None:
    """Extract (home_raw, away_raw) from a Kalshi event title.

    Two formats observed:
      "X at Y: Total Goals"   → US convention, X=AWAY, Y=HOME
      "X vs Y: Totals"        → X=HOME, Y=AWAY

    Returns None if neither delimiter is found.
    """
    clean = _strip_title_suffix(title)
    if not clean:
        return None

    if _AT_PATTERN.search(clean):
        parts = _AT_PATTERN.split(clean, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            # "X at Y" → X=away, Y=home
            return parts[1].strip(), parts[0].strip()
    if _VS_PATTERN.search(clean):
        parts = _VS_PATTERN.split(clean, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            # "X vs Y" → X=home, Y=away
            return parts[0].strip(), parts[1].strip()
    return None


def _load_canonical_teams(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Return {raw_name: team_id} from team_aliases (football_data source)."""
    rows = con.execute(
        "SELECT raw_name, team_id FROM team_aliases WHERE source = 'football_data'"
    ).fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


def _load_existing_kalshi_aliases(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute("SELECT event_ticker FROM kalshi_event_aliases").fetchall()
    return {str(r[0]) for r in rows}


def _insert_alias(
    con: duckdb.DuckDBPyConnection,
    event_ticker: str,
    fixture_id: str,
    confidence: float,
    resolved_by: str,
    dry_run: bool,
) -> None:
    now = datetime.now(tz=UTC)
    if dry_run:
        print(
            f"  [DRY RUN] would insert alias: {event_ticker!r} -> fixture_id={fixture_id!r} "
            f"(conf={confidence:.2f}, by={resolved_by})"
        )
        return
    con.execute(
        """
        INSERT INTO kalshi_event_aliases
            (event_ticker, fixture_id, confidence, resolved_by, resolved_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (event_ticker) DO UPDATE SET
            fixture_id   = excluded.fixture_id,
            confidence   = excluded.confidence,
            resolved_by  = excluded.resolved_by,
            resolved_at  = excluded.resolved_at
        """,
        [event_ticker, fixture_id, confidence, resolved_by, now],
    )
    print(f"  OK: {event_ticker!r} -> {fixture_id!r} (by={resolved_by})")


def _fuzzy_match_team(
    name: str,
    canonical_names: list[str],
    threshold: int,
) -> list[tuple[str, float]]:
    """Return top-3 (canonical_name, score) above threshold."""
    top = process.extract(name, canonical_names, scorer=fuzz.token_set_ratio, limit=3)
    return [(raw, score) for raw, score, _ in top if score >= threshold]


def _find_fixture_id(
    con: duckdb.DuckDBPyConnection,
    home_team_id: str,
    away_team_id: str,
    kickoff_date: date,
) -> str | None:
    """Date-aware future-only fixture match.

    Query v_fixtures_epl on (home, away, date ± 1d) where status != 'final'.
    Multiple matches → pick closest by absolute day delta, WARN.
    """
    rows = con.execute(
        """
        SELECT fixture_id, match_date
        FROM v_fixtures_epl
        WHERE home_team_id = ?
          AND away_team_id = ?
          AND match_date BETWEEN ? AND ?
          AND status != 'final'
        """,
        [
            home_team_id,
            away_team_id,
            kickoff_date - timedelta(days=1),
            kickoff_date + timedelta(days=1),
        ],
    ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return str(rows[0][0])
    rows.sort(key=lambda r: abs((r[1] - kickoff_date).days))
    print(
        f"  WARN: ambiguous fixture match ({len(rows)} candidates); picking "
        f"closest-date {rows[0][0]!r}"
    )
    return str(rows[0][0])


def _compute_season(kickoff_date: date) -> str:
    """EPL season runs Aug→May. Aug 2025–May 2026 → '2025-2026'."""
    if kickoff_date.month >= 8:
        return f"{kickoff_date.year}-{kickoff_date.year + 1}"
    return f"{kickoff_date.year - 1}-{kickoff_date.year}"


def _create_synthetic_fixture(
    con: duckdb.DuckDBPyConnection,
    event_ticker: str,
    home_team_id: str,
    away_team_id: str,
    kickoff_date: date,
    dry_run: bool,
) -> str:
    """Insert (or no-op) a synthetic_fixtures row and return its fixture_id."""
    fixture_id = f"KXFIX-{event_ticker}"
    if dry_run:
        print(
            f"  [DRY RUN] would create synthetic fixture: {fixture_id!r} "
            f"({home_team_id} vs {away_team_id} on {kickoff_date.isoformat()})"
        )
        return fixture_id
    kickoff_utc = datetime.combine(kickoff_date, time(12, 0), tzinfo=UTC)
    season = _compute_season(kickoff_date)
    con.execute(
        """
        INSERT OR IGNORE INTO synthetic_fixtures
            (fixture_id, league, season, home_team_id, away_team_id,
             match_date, kickoff_utc, event_ticker, status, ingested_at)
        VALUES (?, 'EPL', ?, ?, ?, ?, ?, ?, 'scheduled', ?)
        """,
        [
            fixture_id,
            season,
            home_team_id,
            away_team_id,
            kickoff_date,
            kickoff_utc,
            event_ticker,
            datetime.now(tz=UTC),
        ],
    )
    print(
        f"  CREATED synthetic fixture {fixture_id!r} "
        f"({home_team_id} vs {away_team_id}, {kickoff_date.isoformat()})"
    )
    return fixture_id


def _resolve_event(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    title: str,
    canonical: dict[str, str],
    threshold: int,
    now_utc: datetime,
    create_fixtures: bool,
    dry_run: bool,
) -> tuple[str, str, float, str] | None:
    """Resolve a single Kalshi event to (fixture_id, resolved_by, confidence, detail).

    Returns None if unresolvable. Otherwise the tuple suitable for _insert_alias.
    """
    parts = _parse_ticker(ticker)
    home_id: str | None = None
    away_id: str | None = None
    kickoff_date: date | None = None
    resolved_by_parts: list[str] = []
    confidence = 1.0

    if parts is not None:
        kickoff_date = parts.kickoff_date
        home_id = _resolve_team_by_code(con, parts.home_code)
        away_id = _resolve_team_by_code(con, parts.away_code)
        if home_id and away_id:
            resolved_by_parts.append(
                f"ticker:{parts.home_code}/{parts.away_code}@{kickoff_date.isoformat()}"
            )

    if not (home_id and away_id):
        title_parsed = _parse_teams_from_title(title)
        if title_parsed is None:
            print(f"  NO MATCH: {ticker!r} — title unparsable: {title!r}")
            return None
        home_raw, away_raw = title_parsed
        canonical_names = list(canonical.keys())
        home_matches = _fuzzy_match_team(home_raw, canonical_names, threshold)
        away_matches = _fuzzy_match_team(away_raw, canonical_names, threshold)
        if not home_matches or not away_matches:
            print(
                f"  NO MATCH: {ticker!r} title-fallback failed — "
                f"home={home_raw!r}({len(home_matches)} hits), "
                f"away={away_raw!r}({len(away_matches)} hits)"
            )
            return None
        best_home_name, best_home_score = home_matches[0]
        best_away_name, best_away_score = away_matches[0]
        if min(best_home_score, best_away_score) < FUZZY_ACCEPT_THRESHOLD:
            print(
                f"  NO MATCH: {ticker!r} title-fallback below threshold — "
                f"home={best_home_score:.0f}, away={best_away_score:.0f}"
            )
            return None
        home_id = canonical[best_home_name]
        away_id = canonical[best_away_name]
        confidence = min(best_home_score, best_away_score) / 100.0
        resolved_by_parts.append(f"title:{best_home_score:.0f}/{best_away_score:.0f}")

    if kickoff_date is None:
        # Ticker unparseable AND title-only resolution → cannot date-match. Skip.
        print(f"  NO MATCH: {ticker!r} has no parseable kickoff date")
        return None

    fixture_id = _find_fixture_id(con, home_id, away_id, kickoff_date)
    if fixture_id is not None:
        resolved_by_parts.append("fixture:warehouse")
        return fixture_id, "+".join(resolved_by_parts), confidence, "warehouse"

    if not create_fixtures:
        print(
            f"  NO FIXTURE: {ticker!r} resolved to {home_id} v {away_id} on "
            f"{kickoff_date.isoformat()} but no warehouse fixture; --no-create-fixtures set"
        )
        return None

    today = now_utc.date()
    if not (today - _SYNTHETIC_PAST_TOLERANCE <= kickoff_date <= today + _SYNTHETIC_FUTURE_HORIZON):
        print(
            f"  SKIP: {ticker!r} kickoff {kickoff_date.isoformat()} outside "
            f"synthetic-create window [-1d, +14d] from {today.isoformat()}"
        )
        return None

    fixture_id = _create_synthetic_fixture(con, ticker, home_id, away_id, kickoff_date, dry_run)
    resolved_by_parts.append("fixture:synthetic")
    return fixture_id, "+".join(resolved_by_parts), confidence, "synthetic"


def _process_events(
    events: list[dict[str, Any]],
    con: duckdb.DuckDBPyConnection,
    canonical: dict[str, str],
    existing: set[str],
    threshold: int,
    dry_run: bool,
    create_fixtures: bool,
) -> None:
    now_utc = datetime.now(tz=UTC)
    auto_accepted = 0
    skipped = 0
    synthetic_created = 0

    for event in events:
        ticker = str(event.get("event_ticker", ""))
        title = str(event.get("title", ""))
        if not ticker:
            continue
        if ticker in existing:
            print(f"  already mapped: {ticker!r} — skip")
            continue

        resolution = _resolve_event(
            con, ticker, title, canonical, threshold, now_utc, create_fixtures, dry_run
        )
        if resolution is None:
            skipped += 1
            continue
        fixture_id, resolved_by, confidence, detail = resolution
        if detail == "synthetic":
            synthetic_created += 1
        _insert_alias(con, ticker, fixture_id, confidence, resolved_by, dry_run)
        auto_accepted += 1

    print(
        f"\nProcessed: accepted={auto_accepted}, skipped={skipped}, "
        f"synthetic_created={synthetic_created}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--from-fixture", metavar="PATH", type=Path, help="Load events from JSON file"
    )
    mode.add_argument("--live", action="store_true", help="Fetch from Kalshi API")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--no-create-fixtures",
        action="store_true",
        help="Disable synthetic_fixtures insertion when no warehouse fixture matches.",
    )
    args = parser.parse_args(argv)

    con = duckdb.connect(str(args.db_path))
    apply_migrations(con)
    apply_views(con)

    canonical = _load_canonical_teams(con)
    if not canonical:
        print("ERROR: team_aliases is empty. Run ingestion first.")
        return 1
    print(f"Loaded {len(canonical)} canonical team names.")

    existing = _load_existing_kalshi_aliases(con)
    print(f"Found {len(existing)} existing kalshi_event_aliases rows.")

    if args.live:
        from footy_ev.venues.kalshi import KalshiClient

        client = KalshiClient.from_env()
        resp = client.list_events(series_ticker="KXEPLTOTAL")
        events_models = resp.payload if isinstance(resp.payload, list) else []
        events: list[dict[str, Any]] = [
            {"event_ticker": e.event_ticker, "title": e.title} for e in events_models
        ]
    else:
        fixture_path: Path = args.from_fixture
        if not fixture_path.exists():
            print(f"ERROR: fixture file not found: {fixture_path}")
            return 1
        raw = json.loads(fixture_path.read_text())
        events = raw.get("events", raw) if isinstance(raw, dict) else raw

    print(f"\nProcessing {len(events)} events...\n")
    _process_events(
        events,
        con,
        canonical,
        existing,
        args.threshold,
        args.dry_run,
        create_fixtures=not args.no_create_fixtures,
    )
    print("\nBootstrap complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
