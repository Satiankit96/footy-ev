# ruff: noqa: E402
"""One-off bootstrap script: populate betfair_team_aliases via fuzzy match + review.

Run this script:
  1. After getting a Betfair Delayed Application Key (docs/SETUP_GUIDE.md).
  2. After running the first full season of data (team_aliases populated).
  3. Whenever a new EPL team is promoted that Betfair hasn't matched yet.

Workflow:
  - Calls Betfair listEvents + listMarketCatalogue to collect unique team names.
  - Fuzzy-matches each Betfair name against canonical names in team_aliases
    (using the football_data source, which is the same namespace as v_fixtures_epl).
  - Prints a review table: Betfair name | best match | score | team_id.
  - Operator reviews interactively: y = accept, n = skip, m = manual entry.
  - Accepted rows are inserted into betfair_team_aliases.

Usage:
    python scripts/bootstrap_betfair_aliases.py [--db-path PATH] [--dry-run]

Options:
    --db-path PATH    Path to DuckDB warehouse (default: data/warehouse/footy_ev.duckdb)
    --dry-run         Print matches without writing to DB
    --threshold INT   Minimum rapidfuzz score to show (default: 75)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Allow import from project root when run directly
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

import duckdb
from rapidfuzz import fuzz, process

from footy_ev.db import apply_migrations, apply_views
from footy_ev.venues.betfair import BetfairClient
from footy_ev.venues.resolution import parse_betfair_event_name

DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "warehouse" / "footy_ev.duckdb"
DEFAULT_THRESHOLD = 75
FUZZY_ACCEPT_THRESHOLD = 85  # auto-accept above this; below = show for manual review
EPL_COUNTRY_CODE = "GB"
DAYS_AHEAD = 30


def _get_betfair_client() -> BetfairClient:
    app_key = os.environ.get("BETFAIR_APP_KEY")
    username = os.environ.get("BETFAIR_USERNAME")
    password = os.environ.get("BETFAIR_PASSWORD")
    missing = [
        k
        for k, v in [
            ("BETFAIR_APP_KEY", app_key),
            ("BETFAIR_USERNAME", username),
            ("BETFAIR_PASSWORD", password),
        ]
        if not v
    ]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}")
        print("See docs/SETUP_GUIDE.md to configure Betfair credentials in .env")
        sys.exit(1)
    assert app_key and username and password
    return BetfairClient(app_key=app_key, username=username, password=password)


def _collect_betfair_team_names(client: BetfairClient) -> set[str]:
    """Fetch upcoming EPL events and extract unique team name strings."""
    print(f"Fetching Betfair events (country=GB, days_ahead={DAYS_AHEAD})...")
    events_resp = client.list_events(country_codes=[EPL_COUNTRY_CODE], days_ahead=DAYS_AHEAD)
    event_ids: list[str] = []
    names: set[str] = set()
    if isinstance(events_resp.payload, list):
        for entry in events_resp.payload:
            ev = entry.get("event") if isinstance(entry, dict) else None
            if not ev:
                continue
            eid = ev.get("id")
            if eid:
                event_ids.append(str(eid))
            name = ev.get("name", "")
            if " v " in name:
                home, away = parse_betfair_event_name(name)
                if home:
                    names.add(home)
                if away:
                    names.add(away)
    print(f"Found {len(event_ids)} events, {len(names)} unique team name strings.")
    return names


def _load_canonical_teams(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Return {display_name: team_id} from team_aliases (football_data source)."""
    rows = con.execute(
        "SELECT raw_name, team_id FROM team_aliases WHERE source = 'football_data'"
    ).fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


def _load_existing_betfair_aliases(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Return set of betfair_team_names already in betfair_team_aliases."""
    rows = con.execute("SELECT betfair_team_name FROM betfair_team_aliases").fetchall()
    return {str(r[0]) for r in rows}


def _insert_alias(
    con: duckdb.DuckDBPyConnection,
    betfair_name: str,
    team_id: str,
    confidence: float,
    resolved_by: str,
    dry_run: bool,
) -> None:
    now = datetime.now(tz=UTC)
    if dry_run:
        print(
            f"  [DRY RUN] would insert: {betfair_name!r} → {team_id!r} (conf={confidence:.2f}, by={resolved_by})"
        )
        return
    con.execute(
        """
        INSERT INTO betfair_team_aliases
            (betfair_team_name, team_id, confidence, resolved_by, resolved_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (betfair_team_name) DO UPDATE SET
            team_id     = excluded.team_id,
            confidence  = excluded.confidence,
            resolved_by = excluded.resolved_by,
            resolved_at = excluded.resolved_at
        """,
        [betfair_name, team_id, confidence, resolved_by, now],
    )
    print(f"  ✓ Inserted: {betfair_name!r} → {team_id!r}")


def _interactive_review(
    betfair_name: str,
    matches: list[tuple[str, float, str]],
    con: duckdb.DuckDBPyConnection,
    dry_run: bool,
) -> bool:
    """Show match candidates, prompt operator, return True if accepted."""
    print(f"\nBetfair name: {betfair_name!r}")
    for i, (raw_name, score, team_id) in enumerate(matches[:3]):
        print(f"  [{i + 1}] {raw_name!r} (team_id={team_id!r}, score={score:.0f})")
    print("  [m] Enter team_id manually  [s] Skip")
    while True:
        choice = input("  Choice (1/2/3/m/s): ").strip().lower()
        if choice in ("1", "2", "3"):
            idx = int(choice) - 1
            if idx < len(matches):
                _, score, team_id = matches[idx]
                confidence = score / 100.0
                _insert_alias(con, betfair_name, team_id, confidence, "fuzzy_reviewed", dry_run)
                return True
        elif choice == "m":
            team_id_input = input("  Enter team_id: ").strip()
            if team_id_input:
                _insert_alias(con, betfair_name, team_id_input, 1.0, "manual", dry_run)
                return True
        elif choice in ("s", ""):
            print(f"  Skipping {betfair_name!r}")
            return False
        else:
            print("  Invalid — enter 1, 2, 3, m, or s")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Print matches without DB writes")
    parser.add_argument(
        "--threshold", type=int, default=DEFAULT_THRESHOLD, help="Min score to show (0-100)"
    )
    parser.add_argument(
        "--no-interactive", action="store_true", help="Skip interactive review (CI-safe)"
    )
    args = parser.parse_args()

    # Open warehouse
    con = duckdb.connect(str(args.db_path))
    apply_migrations(con)
    apply_views(con)

    canonical = _load_canonical_teams(con)
    if not canonical:
        print("ERROR: team_aliases is empty. Run ingestion + seed_team_aliases.sql first.")
        sys.exit(1)
    print(f"Loaded {len(canonical)} canonical team names from team_aliases.")

    existing = _load_existing_betfair_aliases(con)
    print(f"Found {len(existing)} existing betfair_team_aliases rows.")

    # Collect Betfair team names
    client = _get_betfair_client()
    betfair_names = _collect_betfair_team_names(client)

    # Remove already-mapped names
    unmapped = betfair_names - existing
    print(f"\n{len(unmapped)} unmapped Betfair team names to process.\n")

    if not unmapped:
        print("Nothing to do — all Betfair team names are already mapped.")
        return

    canonical_names = list(canonical.keys())
    auto_accepted = 0
    needs_review: list[tuple[str, list[tuple[str, float, str]]]] = []

    for betfair_name in sorted(unmapped):
        # Top-3 fuzzy matches using token_set_ratio (handles word-order differences)
        top = process.extract(betfair_name, canonical_names, scorer=fuzz.token_set_ratio, limit=3)
        candidates: list[tuple[str, float, str]] = [
            (raw, score, canonical[raw]) for raw, score, _ in top if score >= args.threshold
        ]
        if not candidates:
            print(f"  NO MATCH (below {args.threshold}): {betfair_name!r}")
            continue

        best_raw, best_score, best_team_id = candidates[0]
        if best_score >= FUZZY_ACCEPT_THRESHOLD:
            # Auto-accept
            _insert_alias(
                con,
                betfair_name,
                best_team_id,
                best_score / 100.0,
                f"fuzzy_auto:{best_score:.0f}",
                args.dry_run,
            )
            auto_accepted += 1
        else:
            needs_review.append((betfair_name, candidates))

    print(f"\nAuto-accepted {auto_accepted} aliases (score >= {FUZZY_ACCEPT_THRESHOLD}).")
    print(f"{len(needs_review)} names need manual review.")

    if needs_review and not args.no_interactive:
        print("\n--- Interactive review ---")
        print("For each name, select the best match or enter a team_id manually.\n")
        reviewed = 0
        for betfair_name, candidates in needs_review:
            accepted = _interactive_review(betfair_name, candidates, con, args.dry_run)
            if accepted:
                reviewed += 1
        print(f"\nReview complete. {reviewed}/{len(needs_review)} names mapped.")
    elif needs_review and args.no_interactive:
        print("\nSkipping interactive review (--no-interactive). Unmapped names:")
        for betfair_name, candidates in needs_review:
            best = candidates[0] if candidates else ("?", 0.0, "?")
            print(f"  {betfair_name!r} → best: {best[0]!r} ({best[1]:.0f}) = {best[2]!r}")

    print("\nBootstrap complete.")


if __name__ == "__main__":
    main()
