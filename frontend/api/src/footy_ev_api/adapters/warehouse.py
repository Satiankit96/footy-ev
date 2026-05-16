"""Warehouse explorer adapter — read-only introspection of the DuckDB warehouse.

All queries go through the allowlisted registry or DuckDB's information_schema.
No raw SQL from user input ever reaches the database.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb

from footy_ev_api.errors import AppError
from footy_ev_api.queries.registry import get_query, list_query_names
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)

# Default parameter values for canned queries with optional params.
_PARAM_DEFAULTS: dict[str, Any] = {
    "limit": 20,
    "n": 5,
    "market": "",
}

# Tables with a known timestamp column for last-write display.
_TABLE_TS_COLS: dict[str, str] = {
    "paper_bets": "decided_at",
    "model_predictions": "predicted_at",
    "live_odds_snapshots": "received_at",
    "raw_match_results": "created_at",
    "teams": "created_at",
    "team_aliases": "created_at",
    "kalshi_event_aliases": "resolved_at",
    "synthetic_fixtures": "created_at",
}


def _connect() -> duckdb.DuckDBPyConnection:
    db = Path(Settings().warehouse_path)
    if not db.exists():
        raise AppError("WAREHOUSE_NOT_FOUND", f"Warehouse not found at {db}", 503)
    con = duckdb.connect(str(db), read_only=True)
    from footy_ev.db import apply_migrations, apply_views

    apply_migrations(con)
    apply_views(con)
    return con


def _coerce_value(v: Any) -> Any:
    """Make a DuckDB cell JSON-serialisable."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


# ── Tables overview ────────────────────────────────────────────────────────────


def list_tables() -> dict[str, Any]:
    """Return all user BASE TABLEs with row counts and last-write timestamps."""
    con = _connect()
    try:
        name_rows = con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
        ).fetchall()

        tables: list[dict[str, Any]] = []
        for (table_name,) in name_rows:
            try:
                count_row = con.execute(
                    f"SELECT COUNT(*) FROM {table_name}",  # noqa: S608
                ).fetchone()
                row_count = int(count_row[0]) if count_row else 0
            except duckdb.Error:
                row_count = 0

            last_write: str | None = None
            ts_col = _TABLE_TS_COLS.get(table_name)
            if ts_col:
                try:
                    ts_row = con.execute(
                        f"SELECT MAX(CAST({ts_col} AS VARCHAR)) FROM {table_name}",  # noqa: S608
                    ).fetchone()
                    last_write = str(ts_row[0]) if ts_row and ts_row[0] else None
                except duckdb.Error:
                    last_write = None

            tables.append({"name": table_name, "row_count": row_count, "last_write": last_write})

        return {"tables": tables}
    finally:
        con.close()


# ── Teams ──────────────────────────────────────────────────────────────────────


def list_teams(league: str | None = None) -> dict[str, Any]:
    """Return all teams derived from fixture history, optionally filtered by league."""
    con = _connect()
    try:
        count_rows = con.execute(
            """
            SELECT team_id, league, COUNT(*) AS fixture_count
            FROM (
                SELECT home_team_id AS team_id, league FROM v_fixtures_epl
                UNION ALL
                SELECT away_team_id, league FROM v_fixtures_epl
            ) t
            GROUP BY team_id, league
            ORDER BY fixture_count DESC
            """,
        ).fetchall()

        # Optional league filter
        if league:
            count_rows = [r for r in count_rows if r[1] == league]

        # Merge duplicate team_ids across leagues
        seen: dict[str, dict[str, Any]] = {}
        for r in count_rows:
            tid, lg, cnt = str(r[0]), r[1], int(r[2])
            if tid not in seen:
                seen[tid] = {"team_id": tid, "league": lg, "fixture_count": cnt}
            else:
                seen[tid]["fixture_count"] += cnt

        # Enrich with names from teams table where available
        try:
            name_rows = con.execute(
                "SELECT team_id, name FROM teams",
            ).fetchall()
            names = {str(r[0]): r[1] for r in name_rows}
        except duckdb.CatalogException:
            names = {}

        teams = []
        for entry in seen.values():
            entry["name"] = names.get(entry["team_id"])
            teams.append(entry)

        return {"teams": teams, "total": len(teams)}
    except duckdb.CatalogException:
        return {"teams": [], "total": 0}
    finally:
        con.close()


def get_team(team_id: str) -> dict[str, Any] | None:
    """Return team detail with last-5-game form, or None if team not found."""
    con = _connect()
    try:
        exists_row = con.execute(
            "SELECT 1 FROM v_fixtures_epl WHERE home_team_id = ? OR away_team_id = ? LIMIT 1",
            [team_id, team_id],
        ).fetchone()
        if not exists_row:
            return None

        league_row = con.execute(
            "SELECT league FROM v_fixtures_epl WHERE home_team_id = ? OR away_team_id = ? LIMIT 1",
            [team_id, team_id],
        ).fetchone()
        league: str | None = str(league_row[0]) if league_row and league_row[0] else None

        name: str | None = None
        try:
            name_row = con.execute(
                "SELECT name FROM teams WHERE team_id = ?",
                [team_id],
            ).fetchone()
            name = str(name_row[0]) if name_row and name_row[0] else None
        except duckdb.CatalogException:
            pass

        form: list[dict[str, Any]] = []
        sql = get_query("team_form_last_n")
        if sql:
            try:
                result = con.execute(sql, {"team_id": team_id, "n": 5})
                cols = [d[0] for d in (result.description or [])]
                for row in result.fetchall():
                    form.append(
                        {
                            "fixture_id": str(row[cols.index("fixture_id")]),
                            "date": _coerce_value(row[cols.index("date")]),
                            "opponent_id": str(row[cols.index("opponent_id")]),
                            "home_away": str(row[cols.index("home_away")]),
                            "score": _coerce_value(row[cols.index("score")]),
                            "result": _coerce_value(row[cols.index("result")]),
                            "home_xg": _coerce_value(row[cols.index("home_xg")]),
                            "away_xg": _coerce_value(row[cols.index("away_xg")]),
                        }
                    )
            except (duckdb.CatalogException, duckdb.Error):
                pass

        return {"team_id": team_id, "name": name, "league": league, "form": form}
    except duckdb.CatalogException:
        return None
    finally:
        con.close()


# ── Players (schema has no players table — intentionally empty) ────────────────


def list_players(
    team_id: str | None = None,  # noqa: ARG001
    limit: int = 50,  # noqa: ARG001
    offset: int = 0,  # noqa: ARG001
) -> dict[str, Any]:
    """Return empty player list. No players table exists in this schema."""
    return {
        "players": [],
        "note": "No players table in current schema — squad data not yet ingested.",
    }


# ── Odds snapshots ─────────────────────────────────────────────────────────────


def list_snapshots(
    fixture_id: str | None = None,
    market: str | None = None,
    venue: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Paginated odds-snapshot browser with composable filters."""
    con = _connect()
    try:
        where_parts: list[str] = []
        params: list[Any] = []
        if fixture_id:
            where_parts.append("fixture_id = ?")
            params.append(fixture_id)
        if market:
            where_parts.append("market = ?")
            params.append(market)
        if venue:
            where_parts.append("venue = ?")
            params.append(venue)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        count_row = con.execute(
            f"SELECT COUNT(*) FROM live_odds_snapshots {where_clause}",  # noqa: S608
            params,
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        rows = con.execute(
            f"SELECT fixture_id, venue, market, selection, odds_decimal, "  # noqa: S608
            f"CAST(received_at AS VARCHAR) "
            f"FROM live_odds_snapshots {where_clause} "
            "ORDER BY received_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        snapshots = [
            {
                "fixture_id": str(r[0]),
                "venue": str(r[1]),
                "market": str(r[2]),
                "selection": str(r[3]),
                "odds_decimal": float(r[4]) if r[4] is not None else None,
                "received_at": str(r[5]) if r[5] else None,
            }
            for r in rows
        ]

        return {"snapshots": snapshots, "total": total}
    except duckdb.CatalogException:
        return {"snapshots": [], "total": 0}
    finally:
        con.close()


# ── Canned-query execution ─────────────────────────────────────────────────────


def run_canned_query(query_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a named query from the allowlist. Raises AppError for unknown names.

    Args:
        query_name: stem of a .sql file in the queries/ directory.
        params: named parameters to bind. Caller supplies typed values; defaults
            from _PARAM_DEFAULTS fill in common omissions.

    Returns:
        Dict with columns, rows (list-of-list), and row_count.
    """
    sql = get_query(query_name)
    if sql is None:
        allowed = list_query_names()
        raise AppError(
            "UNKNOWN_QUERY",
            f"'{query_name}' is not in the query allowlist. Allowed: {', '.join(allowed)}",
            400,
        )

    merged: dict[str, Any] = {**_PARAM_DEFAULTS, **params}

    con = _connect()
    try:
        result = con.execute(sql, merged)
        columns = [d[0] for d in (result.description or [])]
        raw_rows = result.fetchall()
        rows = [[_coerce_value(cell) for cell in row] for row in raw_rows]
        return {
            "query_name": query_name,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }
    except duckdb.Error as exc:
        raise AppError("QUERY_FAILED", str(exc), 422) from exc
    finally:
        con.close()
