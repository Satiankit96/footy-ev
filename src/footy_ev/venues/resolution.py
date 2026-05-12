"""Kalshi entity resolution — pure logic, no I/O side effects.

Resolution maps a Kalshi event ticker to a warehouse fixture_id via a
deterministic SQL lookup in kalshi_event_aliases (populated by
scripts/bootstrap_kalshi_aliases.py). No fuzzy matching at runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb

_LOG = logging.getLogger(__name__)


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
        event_ticker: Kalshi event ticker, e.g. "KXEPLTOTAL-26MAY24WHULEE".

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
    kr = resolve_kalshi_market(con, "KXEPLTOTAL-26MAY24WHULEE")
    print(f"smoke: resolve_kalshi_market (unresolved expected) → {kr.status}")
