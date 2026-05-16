"""Canned-query registry for the warehouse query allowlist.

Each .sql file in this directory is one allowed query. The registry loads them
at startup and exposes them by stem name (filename without .sql).

Design rationale: the allowlist approach lets the operator browse data without
exposing an arbitrary SQL execution surface. Any query_name not in this registry
is rejected with HTTP 400 before it ever touches the database.
"""

from __future__ import annotations

from pathlib import Path

_QUERIES_DIR = Path(__file__).parent

_REGISTRY: dict[str, str] | None = None


def _load() -> dict[str, str]:
    registry: dict[str, str] = {}
    for sql_file in sorted(_QUERIES_DIR.glob("*.sql")):
        registry[sql_file.stem] = sql_file.read_text(encoding="utf-8")
    return registry


def get_registry() -> dict[str, str]:
    """Return the loaded registry (lazy-loaded once at first call)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load()
    return _REGISTRY


def get_query(name: str) -> str | None:
    """Return the SQL for the named query, or None if not in the allowlist."""
    return get_registry().get(name)


def list_query_names() -> list[str]:
    """Return sorted list of all allowed query names."""
    return sorted(get_registry().keys())
