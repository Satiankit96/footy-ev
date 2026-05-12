"""Query-time Betfair entity resolution — pure logic, no I/O side effects.

Resolution policy (CLAUDE.md invariant):
  Runtime resolution is a deterministic SQL join — never fuzzy. The
  bootstrap script (scripts/bootstrap_betfair_aliases.py) is the ONLY
  place fuzzy matching runs, and only with manual operator review.

Three resolution calls:
  resolve_event   — Betfair event (home/away name + kickoff) → warehouse fixture_id
  resolve_market  — Betfair market type code → internal market string
  resolve_selection — (internal market, Betfair runner name) → internal selection string

EventResolution fields:
  fixture_id   — warehouse fixture_id (None when status != "resolved")
  confidence   — 1.0 = both teams matched exactly; 0.9 = one name variant matched
  status       — "resolved" | "ambiguous" | "unresolved"
  reason       — human-readable diagnostic

Kickoff alignment: v_fixtures_epl.kickoff_utc is midnight UTC (day-level
precision). We match on DATE(kickoff_utc) = DATE(betfair_kickoff) so the
±6h concept in the spec maps to a same-date comparison that is correct for
any European kick-off time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventResolution:
    """Outcome of a single Betfair event → warehouse fixture resolution."""

    fixture_id: str | None
    confidence: float
    status: str  # "resolved" | "ambiguous" | "unresolved"
    reason: str


def resolve_event(
    con: duckdb.DuckDBPyConnection,
    betfair_event_id: str,
    home_raw: str,
    away_raw: str,
    kickoff_utc: datetime | None,
) -> EventResolution:
    """Resolve a Betfair event to a warehouse fixture_id via SQL join.

    Algorithm:
      1. Look up home_raw and away_raw in betfair_team_aliases → team_ids.
      2. If both resolve, query v_fixtures_epl for a fixture with those
         team_ids on the same calendar date (UTC) as kickoff_utc.
      3. If exactly one row → "resolved". If zero → "unresolved". If >1 →
         "ambiguous".
      4. If either team name is missing from betfair_team_aliases →
         "unresolved" with a diagnostic reason.

    Args:
        con: open DuckDB connection (read access sufficient).
        betfair_event_id: the Betfair event ID (for logging only).
        home_raw: Betfair home team name, as it appears in the event name.
        away_raw: Betfair away team name.
        kickoff_utc: UTC kick-off time from the Betfair event. May be None
            when the Betfair event lacks an openDate — in that case
            resolution falls back to team-only matching (no date filter)
            and confidence is capped at 0.8.

    Returns:
        EventResolution with status, fixture_id (or None), confidence, reason.
    """
    # Step 1: look up team aliases
    home_row = con.execute(
        "SELECT team_id, confidence FROM betfair_team_aliases WHERE betfair_team_name = ?",
        [home_raw],
    ).fetchone()
    away_row = con.execute(
        "SELECT team_id, confidence FROM betfair_team_aliases WHERE betfair_team_name = ?",
        [away_raw],
    ).fetchone()

    missing: list[str] = []
    if home_row is None:
        missing.append(home_raw)
    if away_row is None:
        missing.append(away_raw)
    if missing:
        return EventResolution(
            fixture_id=None,
            confidence=0.0,
            status="unresolved",
            reason=f"no betfair_team_aliases for: {', '.join(missing)}",
        )

    assert home_row is not None  # guarded by `if missing: return` above
    assert away_row is not None
    home_team_id = str(home_row[0])
    away_team_id = str(away_row[0])
    alias_confidence = min(float(home_row[1]), float(away_row[1]))

    # Step 2: find matching fixture
    if kickoff_utc is not None:
        rows = con.execute(
            """
            SELECT fixture_id
            FROM v_fixtures_epl
            WHERE home_team_id = ?
              AND away_team_id = ?
              AND CAST(kickoff_utc AS DATE) = CAST(? AS DATE)
            """,
            [home_team_id, away_team_id, kickoff_utc],
        ).fetchall()
    else:
        # No kickoff: team-only match, confidence capped at 0.8
        rows = con.execute(
            """
            SELECT fixture_id
            FROM v_fixtures_epl
            WHERE home_team_id = ?
              AND away_team_id = ?
            ORDER BY kickoff_utc DESC
            LIMIT 5
            """,
            [home_team_id, away_team_id],
        ).fetchall()
        alias_confidence = min(alias_confidence, 0.8)

    if len(rows) == 0:
        return EventResolution(
            fixture_id=None,
            confidence=0.0,
            status="unresolved",
            reason=(
                f"no fixture found for {home_team_id} v {away_team_id}"
                + (f" on {kickoff_utc.date()}" if kickoff_utc else " (no date)")
            ),
        )
    if len(rows) > 1:
        fixture_ids = [r[0] for r in rows]
        return EventResolution(
            fixture_id=None,
            confidence=0.0,
            status="ambiguous",
            reason=(
                f"{len(rows)} fixtures found for {home_team_id} v {away_team_id}: "
                + ", ".join(fixture_ids[:3])
            ),
        )

    return EventResolution(
        fixture_id=str(rows[0][0]),
        confidence=alias_confidence,
        status="resolved",
        reason=f"{home_team_id} v {away_team_id}",
    )


def resolve_market(
    con: duckdb.DuckDBPyConnection,
    betfair_market_type: str,
) -> str | None:
    """Resolve a Betfair market type code to an internal market string.

    Args:
        con: open DuckDB connection.
        betfair_market_type: e.g. "OVER_UNDER_25".

    Returns:
        Internal market string (e.g. "ou_2.5") or None if unmapped.
    """
    row = con.execute(
        "SELECT internal_market FROM betfair_market_aliases WHERE betfair_market_type = ?",
        [betfair_market_type],
    ).fetchone()
    return str(row[0]) if row else None


def resolve_selection(
    con: duckdb.DuckDBPyConnection,
    internal_market: str,
    betfair_runner_name: str,
) -> str | None:
    """Resolve a Betfair runner name to an internal selection key.

    Args:
        con: open DuckDB connection.
        internal_market: e.g. "ou_2.5".
        betfair_runner_name: e.g. "Over 2.5 Goals".

    Returns:
        Internal selection string (e.g. "over") or None if unmapped.
    """
    row = con.execute(
        """
        SELECT internal_selection
        FROM betfair_selection_aliases
        WHERE internal_market = ? AND betfair_runner_name = ?
        """,
        [internal_market, betfair_runner_name],
    ).fetchone()
    return str(row[0]) if row else None


def cache_resolution(
    con: duckdb.DuckDBPyConnection,
    betfair_event_id: str,
    resolution: EventResolution,
) -> None:
    """Upsert resolution result into betfair_event_resolutions cache.

    Args:
        con: open DuckDB connection (write access required).
        betfair_event_id: Betfair event ID being cached.
        resolution: result from resolve_event.
    """
    now = datetime.now(tz=UTC)
    con.execute(
        """
        INSERT INTO betfair_event_resolutions
            (betfair_event_id, fixture_id, confidence, resolved_at, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (betfair_event_id) DO UPDATE SET
            fixture_id   = excluded.fixture_id,
            confidence   = excluded.confidence,
            resolved_at  = excluded.resolved_at,
            status       = excluded.status
        """,
        [
            betfair_event_id,
            resolution.fixture_id,
            resolution.confidence,
            now,
            resolution.status,
        ],
    )


def parse_betfair_event_name(event_name: str) -> tuple[str, str]:
    """Split a Betfair event name into (home_raw, away_raw).

    Betfair formats event names as "{HomeTeam} v {AwayTeam}". We split on
    " v " (space-v-space) to preserve team names that contain "v" (e.g.
    "Valencia"). The split is right-most to handle rare cases like
    "Man City v Man Utd v Others" (last " v " is the separator).

    Args:
        event_name: full event name string from Betfair.

    Returns:
        (home_raw, away_raw) strings. If " v " is not present, returns
        (event_name, "") so the caller can detect the failure.
    """
    sep = " v "
    idx = event_name.rfind(sep)
    if idx == -1:
        return event_name.strip(), ""
    return event_name[:idx].strip(), event_name[idx + len(sep) :].strip()


def parse_betfair_opendate(open_date_str: str) -> datetime | None:
    """Parse Betfair openDate ISO string to UTC datetime.

    Args:
        open_date_str: ISO8601 string, typically "2024-05-15T14:00:00.000Z".

    Returns:
        UTC datetime or None if parsing fails.
    """
    if not open_date_str:
        return None
    try:
        return datetime.fromisoformat(open_date_str.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def resolve_event_from_meta(
    con: duckdb.DuckDBPyConnection,
    betfair_event_id: str,
    event_meta: dict[str, Any],
) -> EventResolution:
    """Convenience wrapper: resolve using raw Betfair event metadata dict.

    Args:
        con: open DuckDB connection.
        betfair_event_id: Betfair event ID.
        event_meta: dict with keys "name", "openDate", "countryCode" (all optional).

    Returns:
        EventResolution.
    """
    name = str(event_meta.get("name", ""))
    if not name:
        return EventResolution(
            fixture_id=None,
            confidence=0.0,
            status="unresolved",
            reason="empty event name in Betfair metadata",
        )

    home_raw, away_raw = parse_betfair_event_name(name)
    if not away_raw:
        return EventResolution(
            fixture_id=None,
            confidence=0.0,
            status="unresolved",
            reason=f"could not parse home/away from event name: {name!r}",
        )

    kickoff_utc = parse_betfair_opendate(str(event_meta.get("openDate", "")))
    return resolve_event(con, betfair_event_id, home_raw, away_raw, kickoff_utc)


@dataclass(frozen=True)
class KalshiMarketResolution:
    """Outcome of a Kalshi event ticker → warehouse fixture resolution."""

    fixture_id: str | None
    confidence: float
    status: str  # "resolved" | "unresolved"
    reason: str


def resolve_kalshi_market(
    con: duckdb.DuckDBPyConnection,
    event_ticker: str,
) -> KalshiMarketResolution:
    """Resolve a Kalshi event ticker to a warehouse fixture_id via SQL join.

    Looks up the event_ticker in kalshi_event_aliases (populated by
    scripts/bootstrap_kalshi_aliases.py --from-fixture). Resolution is a
    simple primary-key lookup — no fuzzy matching at runtime.

    Args:
        con: open DuckDB connection (read access sufficient).
        event_ticker: Kalshi event ticker, e.g. "kxepltotal-26may01leebur".

    Returns:
        KalshiMarketResolution with status "resolved" (fixture_id set) or
        "unresolved" (fixture_id=None, reason explains why).
    """
    row = con.execute(
        "SELECT fixture_id, confidence FROM kalshi_event_aliases WHERE event_ticker = ?",
        [event_ticker],
    ).fetchone()
    if row is None:
        return KalshiMarketResolution(
            fixture_id=None,
            confidence=0.0,
            status="unresolved",
            reason=(
                f"no kalshi_event_aliases entry for ticker {event_ticker!r}. "
                "Run scripts/bootstrap_kalshi_aliases.py --from-fixture to populate."
            ),
        )
    return KalshiMarketResolution(
        fixture_id=str(row[0]),
        confidence=float(row[1]),
        status="resolved",
        reason=f"alias lookup: {event_ticker!r} → fixture_id={row[0]!r}",
    )


def cache_kalshi_resolution(
    con: duckdb.DuckDBPyConnection,
    event_ticker: str,
    resolution: KalshiMarketResolution,
) -> None:
    """Upsert a Kalshi resolution result into kalshi_contract_resolutions.

    Args:
        con: open DuckDB connection (write access required).
        event_ticker: Kalshi event ticker being cached.
        resolution: result from resolve_kalshi_market.
    """
    now = datetime.now(tz=UTC)
    con.execute(
        """
        INSERT INTO kalshi_contract_resolutions
            (event_ticker, fixture_id, confidence, resolved_at, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (event_ticker) DO UPDATE SET
            fixture_id   = excluded.fixture_id,
            confidence   = excluded.confidence,
            resolved_at  = excluded.resolved_at,
            status       = excluded.status
        """,
        [
            event_ticker,
            resolution.fixture_id,
            resolution.confidence,
            now,
            resolution.status,
        ],
    )


if __name__ == "__main__":
    con = duckdb.connect(":memory:")
    from footy_ev.db import apply_migrations, apply_views

    apply_migrations(con)
    apply_views(con)
    r = resolve_market(con, "OVER_UNDER_25")
    print(f"smoke: OVER_UNDER_25 → {r}")
    s = resolve_selection(con, "ou_2.5", "Over 2.5 Goals")
    print(f"smoke: (ou_2.5, 'Over 2.5 Goals') → {s}")
    kr = resolve_kalshi_market(con, "kxepltotal-26may01leebur")
    print(f"smoke: resolve_kalshi_market (unresolved expected) → {kr.status}")
