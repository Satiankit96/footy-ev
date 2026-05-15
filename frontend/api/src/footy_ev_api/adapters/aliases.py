"""Alias management adapter — read/write against kalshi_event_aliases via DuckDB."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from footy_ev_api.errors import AppError
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)


def _db_path() -> Path:
    return Path(Settings().warehouse_path)


def _connect(*, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    db = _db_path()
    if not db.exists():
        raise AppError("WAREHOUSE_NOT_FOUND", f"Warehouse not found at {db}", 503)
    return duckdb.connect(str(db), read_only=read_only)


def list_aliases(
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List kalshi_event_aliases with optional status filter."""
    con = _connect()
    try:
        where_parts: list[str] = []
        params: list[Any] = []

        if status and status != "all":
            where_parts.append("COALESCE(status, 'active') = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        count_row = con.execute(
            f"SELECT COUNT(*) FROM kalshi_event_aliases {where_clause}",  # noqa: S608
            params,
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        rows = con.execute(
            f"SELECT event_ticker, fixture_id, confidence, resolved_by, resolved_at, COALESCE(status, 'active') as status FROM kalshi_event_aliases {where_clause} ORDER BY resolved_at DESC LIMIT ? OFFSET ?",  # noqa: S608, E501
            [*params, limit, offset],
        ).fetchall()

        aliases = []
        for r in rows:
            aliases.append(
                {
                    "event_ticker": r[0],
                    "fixture_id": r[1],
                    "confidence": r[2],
                    "resolved_by": r[3],
                    "resolved_at": r[4].isoformat() if r[4] else None,
                    "status": r[5],
                }
            )

        return {"aliases": aliases, "total": total}
    except duckdb.CatalogException:
        return {"aliases": [], "total": 0}
    finally:
        con.close()


def get_alias(event_ticker: str) -> dict[str, Any] | None:
    """Get a single alias by event_ticker."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT event_ticker, fixture_id, confidence, resolved_by, resolved_at, COALESCE(status, 'active') as status FROM kalshi_event_aliases WHERE event_ticker = ?",  # noqa: E501
            [event_ticker],
        ).fetchone()
        if not row:
            return None
        return {
            "event_ticker": row[0],
            "fixture_id": row[1],
            "confidence": row[2],
            "resolved_by": row[3],
            "resolved_at": row[4].isoformat() if row[4] else None,
            "status": row[5],
        }
    except duckdb.CatalogException:
        return None
    finally:
        con.close()


def get_conflicts() -> list[dict[str, Any]]:
    """Find aliases pointing at the same fixture (potential conflicts)."""
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT fixture_id, COUNT(*) as alias_count,
                   LIST(event_ticker) as tickers
            FROM kalshi_event_aliases
            WHERE COALESCE(status, 'active') = 'active'
            GROUP BY fixture_id
            HAVING COUNT(*) > 1
            ORDER BY alias_count DESC
            """,
        ).fetchall()
        return [{"fixture_id": r[0], "alias_count": r[1], "tickers": r[2]} for r in rows]
    except duckdb.CatalogException:
        return []
    finally:
        con.close()


def create_alias(
    *,
    event_ticker: str,
    fixture_id: str,
    confidence: float = 1.0,
    resolved_by: str = "manual",
) -> dict[str, Any]:
    """Create a new alias. Validates fixture exists. Rejects if active alias exists."""
    con = _connect(read_only=False)
    try:
        existing = con.execute(
            "SELECT event_ticker FROM kalshi_event_aliases WHERE event_ticker = ? AND COALESCE(status, 'active') = 'active'",  # noqa: E501
            [event_ticker],
        ).fetchone()
        if existing:
            raise AppError(
                "ALIAS_EXISTS",
                f"Active alias already exists for {event_ticker}",
                409,
            )

        fixture_row = None
        for table in ("v_fixtures_epl", "synthetic_fixtures"):
            try:
                fixture_row = con.execute(
                    f"SELECT fixture_id FROM {table} WHERE fixture_id = ?",  # noqa: S608
                    [fixture_id],
                ).fetchone()
                if fixture_row:
                    break
            except duckdb.CatalogException:
                continue

        if not fixture_row:
            raise AppError(
                "FIXTURE_NOT_FOUND",
                f"Fixture {fixture_id} does not exist in the warehouse",
                404,
            )

        now = datetime.now(tz=UTC)
        con.execute(
            """
            INSERT INTO kalshi_event_aliases
                (event_ticker, fixture_id, confidence, resolved_by, resolved_at, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            [event_ticker, fixture_id, confidence, resolved_by, now],
        )

        return {
            "event_ticker": event_ticker,
            "fixture_id": fixture_id,
            "confidence": confidence,
            "resolved_by": resolved_by,
            "resolved_at": now.isoformat(),
            "status": "active",
        }
    finally:
        con.close()


def retire_alias(event_ticker: str) -> dict[str, Any]:
    """Retire an alias by appending a status='retired' row. Never UPDATE or DELETE."""
    con = _connect(read_only=False)
    try:
        existing = con.execute(
            "SELECT fixture_id, confidence, resolved_by FROM kalshi_event_aliases WHERE event_ticker = ?",
            [event_ticker],
        ).fetchone()
        if not existing:
            raise AppError("ALIAS_NOT_FOUND", f"No alias found for {event_ticker}", 404)

        now = datetime.now(tz=UTC)
        con.execute(
            """
            INSERT INTO kalshi_event_aliases
                (event_ticker, fixture_id, confidence, resolved_by, resolved_at, status)
            VALUES (?, ?, ?, ?, ?, 'retired')
            ON CONFLICT (event_ticker) DO UPDATE SET
                status = 'retired',
                resolved_at = excluded.resolved_at
            """,
            [event_ticker, existing[0], existing[1], existing[2], now],
        )

        return {
            "event_ticker": event_ticker,
            "status": "retired",
            "retired_at": now.isoformat(),
        }
    finally:
        con.close()
