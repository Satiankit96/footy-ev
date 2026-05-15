"""Fixtures adapter — read-only queries against v_fixtures_epl via DuckDB."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from footy_ev_api.errors import AppError
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)


def _db_path() -> Path:
    return Path(Settings().warehouse_path)


def _connect() -> duckdb.DuckDBPyConnection:
    db = _db_path()
    if not db.exists():
        raise AppError("WAREHOUSE_NOT_FOUND", f"Warehouse not found at {db}", 503)
    con = duckdb.connect(str(db), read_only=True)
    from footy_ev.db import apply_migrations, apply_views

    apply_migrations(con)
    apply_views(con)
    return con


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "fixture_id": row[0],
        "league": row[1],
        "season": row[2],
        "home_team_id": row[3],
        "away_team_id": row[4],
        "home_team_raw": row[5],
        "away_team_raw": row[6],
        "match_date": row[7].isoformat() if row[7] else None,
        "kickoff_utc": row[8].isoformat() if row[8] else None,
        "home_score_ft": row[9],
        "away_score_ft": row[10],
        "result_ft": row[11],
        "home_xg": str(row[12]) if row[12] is not None else None,
        "away_xg": str(row[13]) if row[13] is not None else None,
        "status": row[14],
    }


_BASE_COLS = (
    "fixture_id, league, season, home_team_id, away_team_id, "
    "home_team_raw, away_team_raw, match_date, kickoff_utc, "
    "home_score_ft, away_score_ft, result_ft, home_xg, away_xg, status"
)


def list_fixtures(
    *,
    status: str | None = None,
    league: str | None = None,
    season: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Paginated fixture list with composable filters."""
    con = _connect()
    try:
        where_parts: list[str] = []
        params: list[Any] = []

        if status:
            where_parts.append("status = ?")
            params.append(status)
        if league:
            where_parts.append("league = ?")
            params.append(league)
        if season:
            where_parts.append("season = ?")
            params.append(season)
        if date_from:
            where_parts.append("match_date >= CAST(? AS DATE)")
            params.append(date_from)
        if date_to:
            where_parts.append("match_date <= CAST(? AS DATE)")
            params.append(date_to)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        count_row = con.execute(
            f"SELECT COUNT(*) FROM v_fixtures_epl {where_clause}",  # noqa: S608
            params,
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        rows = con.execute(
            f"SELECT {_BASE_COLS} FROM v_fixtures_epl {where_clause} "  # noqa: S608
            "ORDER BY match_date DESC, fixture_id "
            "LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        fixtures = [_row_to_dict(r) for r in rows]

        alias_counts = _get_alias_counts(con, [f["fixture_id"] for f in fixtures])
        for f in fixtures:
            f["alias_count"] = alias_counts.get(f["fixture_id"], 0)

        return {"fixtures": fixtures, "total": total}
    except duckdb.CatalogException as exc:
        _LOG.warning("Fixtures query failed: %s", exc)
        return {"fixtures": [], "total": 0}
    finally:
        con.close()


def get_fixture(fixture_id: str) -> dict[str, Any] | None:
    """Single fixture with linked aliases and prediction/bet counts."""
    con = _connect()
    try:
        row = con.execute(
            f"SELECT {_BASE_COLS} FROM v_fixtures_epl WHERE fixture_id = ?",  # noqa: S608
            [fixture_id],
        ).fetchone()
        if not row:
            return None

        fixture = _row_to_dict(row)

        aliases: list[dict[str, Any]] = []
        try:
            alias_rows = con.execute(
                "SELECT event_ticker, confidence, resolved_by, resolved_at "
                "FROM kalshi_event_aliases "
                "WHERE fixture_id = ? AND COALESCE(status, 'active') = 'active'",
                [fixture_id],
            ).fetchall()
            for ar in alias_rows:
                aliases.append(
                    {
                        "event_ticker": ar[0],
                        "confidence": ar[1],
                        "resolved_by": ar[2],
                        "resolved_at": ar[3].isoformat() if ar[3] else None,
                    }
                )
        except duckdb.CatalogException:
            pass

        prediction_count = 0
        try:
            pc_row = con.execute(
                "SELECT COUNT(*) FROM model_predictions WHERE fixture_id = ?",
                [fixture_id],
            ).fetchone()
            prediction_count = int(pc_row[0]) if pc_row else 0
        except duckdb.CatalogException:
            pass

        bet_count = 0
        try:
            bc_row = con.execute(
                "SELECT COUNT(*) FROM paper_bets WHERE fixture_id = ?",
                [fixture_id],
            ).fetchone()
            bet_count = int(bc_row[0]) if bc_row else 0
        except duckdb.CatalogException:
            pass

        fixture["aliases"] = aliases
        fixture["prediction_count"] = prediction_count
        fixture["bet_count"] = bet_count

        return fixture
    except duckdb.CatalogException:
        return None
    finally:
        con.close()


def list_upcoming(*, days: int = 14) -> dict[str, Any]:
    """Scheduled fixtures in the next N days with alias status."""
    con = _connect()
    try:
        cutoff = datetime.now(UTC) + timedelta(days=days)

        rows = con.execute(
            f"SELECT {_BASE_COLS} FROM v_fixtures_epl "  # noqa: S608
            "WHERE status = 'scheduled' AND kickoff_utc <= ? "
            "ORDER BY kickoff_utc ASC",
            [cutoff],
        ).fetchall()

        fixtures = [_row_to_dict(r) for r in rows]

        alias_counts = _get_alias_counts(con, [f["fixture_id"] for f in fixtures])
        for f in fixtures:
            f["alias_count"] = alias_counts.get(f["fixture_id"], 0)

        return {"fixtures": fixtures, "total": len(fixtures)}
    except duckdb.CatalogException:
        return {"fixtures": [], "total": 0}
    finally:
        con.close()


def _get_alias_counts(
    con: duckdb.DuckDBPyConnection,
    fixture_ids: list[str],
) -> dict[str, int]:
    """Batch-fetch active alias counts for a list of fixture IDs."""
    if not fixture_ids:
        return {}
    try:
        placeholders = ", ".join("?" for _ in fixture_ids)
        rows = con.execute(
            f"SELECT fixture_id, COUNT(*) FROM kalshi_event_aliases "  # noqa: S608
            f"WHERE fixture_id IN ({placeholders}) AND COALESCE(status, 'active') = 'active' "  # noqa: S608
            "GROUP BY fixture_id",
            fixture_ids,
        ).fetchall()
        return {r[0]: int(r[1]) for r in rows}
    except duckdb.CatalogException:
        return {}
