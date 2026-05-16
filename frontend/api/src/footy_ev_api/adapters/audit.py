"""Audit adapter — operator actions, model versions, bet decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from footy_ev_api.errors import AppError
from footy_ev_api.settings import Settings


def _connect() -> duckdb.DuckDBPyConnection:
    db = Path(Settings().warehouse_path)
    if not db.exists():
        raise AppError("WAREHOUSE_NOT_FOUND", f"Warehouse not found at {db}", 503)
    con = duckdb.connect(str(db), read_only=True)
    from footy_ev.db import apply_migrations, apply_views

    apply_migrations(con)
    apply_views(con)
    return con


def list_operator_actions(
    action_type: str | None = None,
    since: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Paginated operator action log from operator_actions table."""
    con = _connect()
    try:
        where_parts: list[str] = []
        params: list[Any] = []
        if action_type:
            where_parts.append("action_type = ?")
            params.append(action_type)
        if since:
            where_parts.append("performed_at >= CAST(? AS TIMESTAMP)")
            params.append(since)
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        count_row = con.execute(
            f"SELECT COUNT(*) FROM operator_actions {where_clause}",  # noqa: S608
            params,
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        rows = con.execute(
            f"SELECT action_id, action_type, operator, "  # noqa: S608
            f"CAST(performed_at AS VARCHAR), input_params, result_summary, request_id "
            f"FROM operator_actions {where_clause} "
            "ORDER BY performed_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        actions = [
            {
                "action_id": str(r[0]),
                "action_type": str(r[1]),
                "operator": str(r[2]),
                "performed_at": str(r[3]),
                "input_params": str(r[4]) if r[4] is not None else None,
                "result_summary": str(r[5]) if r[5] is not None else None,
                "request_id": str(r[6]) if r[6] is not None else None,
            }
            for r in rows
        ]
        return {"actions": actions, "total": total}
    except duckdb.CatalogException:
        return {"actions": [], "total": 0}
    finally:
        con.close()


def list_model_versions() -> dict[str, Any]:
    """Return distinct model versions from model_predictions with first/last seen."""
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT
                model_version,
                CAST(MIN(predicted_at) AS VARCHAR) AS first_seen,
                CAST(MAX(predicted_at) AS VARCHAR) AS last_seen,
                COUNT(*) AS prediction_count
            FROM model_predictions
            GROUP BY model_version
            ORDER BY MAX(predicted_at) DESC
            """,
        ).fetchall()

        versions = [
            {
                "model_version": str(r[0]),
                "first_seen": str(r[1]) if r[1] else None,
                "last_seen": str(r[2]) if r[2] else None,
                "prediction_count": int(r[3]),
            }
            for r in rows
        ]
        return {"versions": versions}
    except duckdb.CatalogException:
        return {"versions": []}
    finally:
        con.close()


def list_decisions(
    since: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Paper bet decision audit trail from paper_bets."""
    con = _connect()
    try:
        where_parts: list[str] = []
        params: list[Any] = []
        if since:
            where_parts.append("decided_at >= CAST(? AS TIMESTAMP)")
            params.append(since)
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        count_row = con.execute(
            f"SELECT COUNT(*) FROM paper_bets {where_clause}",  # noqa: S608
            params,
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        rows = con.execute(
            f"SELECT bet_id, fixture_id, CAST(decided_at AS VARCHAR), "  # noqa: S608
            f"market, selection, CAST(stake_gbp AS VARCHAR), CAST(odds AS VARCHAR), "
            f"edge_pct, settlement_status, prediction_id "
            f"FROM paper_bets {where_clause} "
            "ORDER BY decided_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        decisions = [
            {
                "bet_id": str(r[0]),
                "fixture_id": str(r[1]),
                "decided_at": str(r[2]) if r[2] else None,
                "market": str(r[3]),
                "selection": str(r[4]),
                "stake_gbp": str(r[5]),
                "odds": str(r[6]),
                "edge_pct": float(r[7]) if r[7] is not None else None,
                "settlement_status": str(r[8]),
                "prediction_id": str(r[9]) if r[9] else None,
            }
            for r in rows
        ]
        return {"decisions": decisions, "total": total}
    except duckdb.CatalogException:
        return {"decisions": [], "total": 0}
    finally:
        con.close()
