"""Unit tests for Kalshi entity resolution.

Tests resolve_kalshi_market() and cache_kalshi_resolution() using an
in-memory DuckDB with migration 011 applied.
"""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from footy_ev.db import apply_migrations
from footy_ev.venues.resolution import (
    KalshiMarketResolution,
    cache_kalshi_resolution,
    resolve_kalshi_market,
)


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_migrations(c)
    return c


def _seed_alias(
    con: duckdb.DuckDBPyConnection,
    event_ticker: str,
    fixture_id: str,
    confidence: float = 1.0,
) -> None:
    con.execute(
        """
        INSERT INTO kalshi_event_aliases
            (event_ticker, fixture_id, confidence, resolved_by, resolved_at)
        VALUES (?, ?, ?, 'test', ?)
        """,
        [event_ticker, fixture_id, confidence, datetime.now(tz=UTC)],
    )


# ---------------------------------------------------------------------------
# resolve_kalshi_market
# ---------------------------------------------------------------------------


def test_resolve_kalshi_market_found(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(con, "KXEPLTOTAL-26MAY16ARSLIV", "EPL|2025-2026|arsenal|liverpool|2026-05-16")
    res = resolve_kalshi_market(con, "KXEPLTOTAL-26MAY16ARSLIV")
    assert res.status == "resolved"
    assert res.fixture_id == "EPL|2025-2026|arsenal|liverpool|2026-05-16"
    assert res.confidence == 1.0


def test_resolve_kalshi_market_not_found(con: duckdb.DuckDBPyConnection) -> None:
    res = resolve_kalshi_market(con, "KXEPLTOTAL-UNKNOWN")
    assert res.status == "unresolved"
    assert res.fixture_id is None
    assert "KXEPLTOTAL-UNKNOWN" in res.reason


def test_resolve_kalshi_market_confidence_preserved(con: duckdb.DuckDBPyConnection) -> None:
    _seed_alias(
        con,
        "KXEPLTOTAL-26MAY23TOTMAN",
        "EPL|2025-2026|tottenham|man_utd|2026-05-23",
        confidence=0.92,
    )
    res = resolve_kalshi_market(con, "KXEPLTOTAL-26MAY23TOTMAN")
    assert res.status == "resolved"
    assert abs(res.confidence - 0.92) < 1e-9


# ---------------------------------------------------------------------------
# cache_kalshi_resolution
# ---------------------------------------------------------------------------


def test_cache_kalshi_resolution_write_and_read(con: duckdb.DuckDBPyConnection) -> None:
    res = KalshiMarketResolution(
        fixture_id="EPL|2025-2026|arsenal|liverpool|2026-05-16",
        confidence=0.95,
        status="resolved",
        reason="alias lookup",
    )
    cache_kalshi_resolution(con, "KXEPLTOTAL-26MAY16ARSLIV", res)
    row = con.execute(
        "SELECT fixture_id, confidence, status FROM kalshi_contract_resolutions "
        "WHERE event_ticker = ?",
        ["KXEPLTOTAL-26MAY16ARSLIV"],
    ).fetchone()
    assert row is not None
    assert row[0] == "EPL|2025-2026|arsenal|liverpool|2026-05-16"
    assert abs(float(row[1]) - 0.95) < 1e-9
    assert row[2] == "resolved"


def test_cache_kalshi_resolution_upsert(con: duckdb.DuckDBPyConnection) -> None:
    res1 = KalshiMarketResolution(
        fixture_id=None, confidence=0.0, status="unresolved", reason="not found"
    )
    cache_kalshi_resolution(con, "KXEPLTOTAL-26MAY16ARSLIV", res1)

    res2 = KalshiMarketResolution(
        fixture_id="EPL|2025-2026|arsenal|liverpool|2026-05-16",
        confidence=1.0,
        status="resolved",
        reason="alias lookup",
    )
    cache_kalshi_resolution(con, "KXEPLTOTAL-26MAY16ARSLIV", res2)

    rows = con.execute(
        "SELECT COUNT(*), MAX(status) FROM kalshi_contract_resolutions WHERE event_ticker = ?",
        ["KXEPLTOTAL-26MAY16ARSLIV"],
    ).fetchone()
    assert rows[0] == 1  # upserted, not duplicated
    assert rows[1] == "resolved"


def test_cache_kalshi_resolution_unresolved_fixture_id_null(con: duckdb.DuckDBPyConnection) -> None:
    res = KalshiMarketResolution(
        fixture_id=None, confidence=0.0, status="unresolved", reason="no alias"
    )
    cache_kalshi_resolution(con, "KXEPLTOTAL-NOMATCH", res)
    row = con.execute(
        "SELECT fixture_id, status FROM kalshi_contract_resolutions WHERE event_ticker = ?",
        ["KXEPLTOTAL-NOMATCH"],
    ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] == "unresolved"
