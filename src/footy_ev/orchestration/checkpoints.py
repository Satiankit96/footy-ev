"""DuckDB-side summary writer for langgraph_checkpoint_summaries.

The SQLite saver owns the binary checkpoint blobs; this module just
records one row per graph invocation so the dashboard has something to
query without cracking open SQLite.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import duckdb


def write_summary(
    con: duckdb.DuckDBPyConnection,
    *,
    invocation_id: str,
    fixture_ids: list[str],
    started_at: datetime,
    completed_at: datetime | None,
    final_node: str,
    n_candidate_bets: int,
    n_approved_bets: int,
    breaker_tripped: bool,
    breaker_reason: str | None,
    last_error: str | None,
    sqlite_thread_id: str,
) -> None:
    con.execute(
        """
        INSERT INTO langgraph_checkpoint_summaries (
            invocation_id, fixture_ids, started_at, completed_at,
            final_node, n_candidate_bets, n_approved_bets,
            breaker_tripped, breaker_reason, last_error, sqlite_thread_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (invocation_id) DO NOTHING
        """,
        [
            invocation_id,
            fixture_ids,
            started_at,
            completed_at,
            final_node,
            n_candidate_bets,
            n_approved_bets,
            breaker_tripped,
            breaker_reason,
            last_error,
            sqlite_thread_id,
        ],
    )


def make_invocation_id(fixture_ids: list[str], started_at: datetime) -> str:
    seed = "|".join(sorted(fixture_ids)) + "|" + started_at.isoformat()
    return hashlib.sha256(seed.encode()).hexdigest()[:24]


def log_circuit_breaker(
    con: duckdb.DuckDBPyConnection,
    *,
    reason: str,
    affected_source: str,
    max_staleness_sec: int | None = None,
    tripped_at: datetime | None = None,
) -> None:
    when = tripped_at or datetime.utcnow()
    event_id = hashlib.sha256(
        f"{reason}|{affected_source}|{when.isoformat()}".encode()
    ).hexdigest()[:24]
    con.execute(
        """
        INSERT INTO circuit_breaker_log (
            event_id, tripped_at, reason, affected_source, max_staleness_sec
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (event_id) DO NOTHING
        """,
        [event_id, when, reason, affected_source, max_staleness_sec],
    )


_ = Any  # mypy: keep import unused but available for future typing
