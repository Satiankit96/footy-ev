# ruff: noqa: E402
"""One-off bootstrap script: populate kalshi_event_aliases from fixture file or live API.

Two modes:
  --from-fixture PATH   Read a JSON fixture file (e.g. tests/fixtures/kalshi_events_sample.json)
                        and fuzzy-match event titles against warehouse team_aliases.
                        Safe to run offline; no Kalshi credentials required.

  --live                Call KalshiClient.get_events() against the real API.
                        Raises NotImplementedError until Phase 3 step 5b wires RSA auth.
                        Use --from-fixture until auth is implemented.

Workflow (--from-fixture):
  1. Load the JSON file (list of Kalshi event objects).
  2. For each event, extract team names from the 'title' field (NOT the ticker —
     per Kalshi docs, ticker format is internal and subject to change).
  3. Fuzzy-match each team name against canonical names in team_aliases.
  4. Print a review table.
  5. Operator reviews: y = accept, s = skip, m = manual.
  6. Accepted rows are inserted into kalshi_event_aliases.

Usage:
    python scripts/bootstrap_kalshi_aliases.py --from-fixture tests/fixtures/kalshi_events_sample.json
    python scripts/bootstrap_kalshi_aliases.py --from-fixture PATH --dry-run
    python scripts/bootstrap_kalshi_aliases.py --live           # requires step 5b
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from datetime import UTC, datetime
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

# Patterns for splitting Kalshi event titles like:
#   "Arsenal vs Liverpool - Total Goals"
#   "Manchester City vs Chelsea - Total Goals"
_VS_PATTERN = re.compile(r"\s+vs\s+", re.IGNORECASE)
_SUFFIX_PATTERN = re.compile(r"\s*-\s*total goals.*$", re.IGNORECASE)


def _parse_teams_from_title(title: str) -> tuple[str, str]:
    """Extract (home, away) from a Kalshi event title.

    Uses the event title field (e.g. "Arsenal vs Liverpool - Total Goals")
    per Kalshi docs recommendation to not parse ticker strings.

    Returns:
        (home, away) stripped strings. Both empty string if parsing fails.
    """
    clean = _SUFFIX_PATTERN.sub("", title).strip()
    parts = _VS_PATTERN.split(clean, maxsplit=1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


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
            f"  [DRY RUN] would insert: {event_ticker!r} -> fixture_id={fixture_id!r} "
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
    print(f"  OK: {event_ticker!r} -> {fixture_id!r}")


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
    open_time_str: str,
) -> str | None:
    """SQL join to find fixture_id for a resolved home/away team pair + date.

    Returns fixture_id string or None if no match.
    """
    kickoff: datetime | None = None
    if open_time_str:
        with contextlib.suppress(ValueError):
            kickoff = datetime.fromisoformat(open_time_str.replace("Z", "+00:00")).astimezone(UTC)

    if kickoff is not None:
        rows = con.execute(
            """
            SELECT fixture_id
            FROM v_fixtures_epl
            WHERE home_team_id = ?
              AND away_team_id = ?
              AND CAST(kickoff_utc AS DATE) = CAST(? AS DATE)
            """,
            [home_team_id, away_team_id, kickoff],
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT fixture_id
            FROM v_fixtures_epl
            WHERE home_team_id = ?
              AND away_team_id = ?
            ORDER BY kickoff_utc DESC
            LIMIT 1
            """,
            [home_team_id, away_team_id],
        ).fetchall()

    if len(rows) == 1:
        return str(rows[0][0])
    return None


def _process_from_fixture(
    events: list[dict[str, Any]],
    con: duckdb.DuckDBPyConnection,
    canonical: dict[str, str],
    existing: set[str],
    threshold: int,
    dry_run: bool,
    no_interactive: bool,
) -> None:
    canonical_names = list(canonical.keys())
    auto_accepted = 0
    needs_review: list[tuple[str, str, str]] = []  # (event_ticker, home_raw, away_raw)
    skipped = 0

    for event in events:
        ticker = str(event.get("event_ticker", ""))
        title = str(event.get("title", ""))
        open_time = str(event.get("open_time", ""))

        if not ticker:
            continue
        if ticker in existing:
            print(f"  already mapped: {ticker!r} — skip")
            continue

        home_raw, away_raw = _parse_teams_from_title(title)
        if not home_raw or not away_raw:
            print(f"  WARN: could not parse teams from title {title!r} ({ticker})")
            skipped += 1
            continue

        home_matches = _fuzzy_match_team(home_raw, canonical_names, threshold)
        away_matches = _fuzzy_match_team(away_raw, canonical_names, threshold)

        if not home_matches or not away_matches:
            print(
                f"  NO MATCH: {ticker!r} — home={home_raw!r} ({len(home_matches)} matches), "
                f"away={away_raw!r} ({len(away_matches)} matches)"
            )
            skipped += 1
            continue

        best_home_name, best_home_score = home_matches[0]
        best_away_name, best_away_score = away_matches[0]
        home_team_id = canonical[best_home_name]
        away_team_id = canonical[best_away_name]
        min_score = min(best_home_score, best_away_score)

        if min_score >= FUZZY_ACCEPT_THRESHOLD:
            fixture_id = _find_fixture_id(con, home_team_id, away_team_id, open_time)
            if fixture_id:
                _insert_alias(
                    con,
                    ticker,
                    fixture_id,
                    min_score / 100.0,
                    f"fuzzy_auto:{min_score:.0f}",
                    dry_run,
                )
                auto_accepted += 1
            else:
                print(
                    f"  WARN: {ticker!r} — teams resolved but no warehouse fixture found "
                    f"({home_team_id} v {away_team_id} on {open_time[:10]})"
                )
                skipped += 1
        else:
            needs_review.append((ticker, home_raw, away_raw))

    print(f"\nAuto-accepted: {auto_accepted}  Need review: {len(needs_review)}  Skipped: {skipped}")

    if needs_review and not no_interactive:
        print("\n--- Interactive review ---")
        for ticker, home_raw, away_raw in needs_review:
            event_obj = next((e for e in events if e.get("event_ticker") == ticker), {})
            open_time = str(event_obj.get("open_time", ""))
            print(f"\nTicker: {ticker!r}")
            print(f"  Home raw: {home_raw!r}")
            print(f"  Away raw: {away_raw!r}")
            home_matches = _fuzzy_match_team(home_raw, canonical_names, threshold)
            away_matches = _fuzzy_match_team(away_raw, canonical_names, threshold)
            for i, (nm, sc) in enumerate(home_matches[:3]):
                print(f"    home[{i + 1}] {nm!r} (score={sc:.0f}) team_id={canonical[nm]!r}")
            for i, (nm, sc) in enumerate(away_matches[:3]):
                print(f"    away[{i + 1}] {nm!r} (score={sc:.0f}) team_id={canonical[nm]!r}")
            print("  [a] Accept best match  [m] Enter fixture_id manually  [s] Skip")
            while True:
                choice = input("  Choice (a/m/s): ").strip().lower()
                if choice == "a" and home_matches and away_matches:
                    home_id = canonical[home_matches[0][0]]
                    away_id = canonical[away_matches[0][0]]
                    fixture_id = _find_fixture_id(con, home_id, away_id, open_time)
                    if fixture_id:
                        conf = min(home_matches[0][1], away_matches[0][1]) / 100.0
                        _insert_alias(con, ticker, fixture_id, conf, "fuzzy_reviewed", dry_run)
                    else:
                        print("  WARN: no warehouse fixture found for that team pair + date")
                    break
                if choice == "m":
                    fid = input("  Enter fixture_id: ").strip()
                    if fid:
                        _insert_alias(con, ticker, fid, 1.0, "manual", dry_run)
                    break
                if choice in ("s", ""):
                    print(f"  Skipping {ticker!r}")
                    break
                print("  Invalid — enter a, m, or s")
    elif needs_review and no_interactive:
        print("Skipping interactive review (--no-interactive). Unmapped tickers:")
        for ticker, home_raw, away_raw in needs_review:
            print(f"  {ticker!r}: home={home_raw!r}, away={away_raw!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--from-fixture", metavar="PATH", type=Path, help="Load events from JSON file"
    )
    mode.add_argument("--live", action="store_true", help="Fetch from Kalshi API (needs step 5b)")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--no-interactive", action="store_true")
    args = parser.parse_args()

    con = duckdb.connect(str(args.db_path))
    apply_migrations(con)
    apply_views(con)

    canonical = _load_canonical_teams(con)
    if not canonical:
        print("ERROR: team_aliases is empty. Run ingestion first.")
        sys.exit(1)
    print(f"Loaded {len(canonical)} canonical team names.")

    existing = _load_existing_kalshi_aliases(con)
    print(f"Found {len(existing)} existing kalshi_event_aliases rows.")

    if args.live:
        from footy_ev.venues.kalshi import KalshiClient

        client = KalshiClient.from_env()
        resp = client.list_events(series_ticker="KXEPLTOTAL")
        events_models = resp.payload if isinstance(resp.payload, list) else []
        # Convert KalshiEvent objects to dicts compatible with _process_from_fixture
        events: list[dict[str, Any]] = [
            {"event_ticker": e.event_ticker, "title": e.title, "open_time": ""}
            for e in events_models
        ]
    else:
        fixture_path: Path = args.from_fixture
        if not fixture_path.exists():
            print(f"ERROR: fixture file not found: {fixture_path}")
            sys.exit(1)
        raw = json.loads(fixture_path.read_text())
        events = raw.get("events", raw) if isinstance(raw, dict) else raw

    print(f"\nProcessing {len(events)} events...\n")
    _process_from_fixture(
        events, con, canonical, existing, args.threshold, args.dry_run, args.no_interactive
    )
    print("\nBootstrap complete.")


if __name__ == "__main__":
    main()
