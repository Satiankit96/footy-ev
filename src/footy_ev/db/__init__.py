"""DuckDB connection helpers and simple migration runner.

The runner applies every ``*.sql`` file in ``migrations/`` in lexical order. There
is no version-tracking table yet — migrations must be idempotent (use
``CREATE TABLE IF NOT EXISTS``, ``CREATE INDEX IF NOT EXISTS``, etc.). Add a
``_migrations`` ledger once we have a migration that can't be expressed idempotently.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
VIEWS_DIR = Path(__file__).parent / "views"


def apply_migrations(
    con: duckdb.DuckDBPyConnection,
    migrations_dir: Path | None = None,
) -> list[str]:
    """Apply every ``.sql`` file in ``migrations_dir`` in lexical order.

    Args:
        con: Open DuckDB connection to apply migrations against.
        migrations_dir: Directory to scan. Defaults to the package's ``migrations/``.

    Returns:
        List of migration filenames applied, in application order.
    """
    mdir = migrations_dir or MIGRATIONS_DIR
    applied: list[str] = []
    for sql_file in sorted(mdir.glob("*.sql")):
        con.execute(sql_file.read_text(encoding="utf-8"))
        applied.append(sql_file.name)
    return applied


def apply_views(
    con: duckdb.DuckDBPyConnection,
    views_dir: Path | None = None,
) -> list[str]:
    """Apply every ``.sql`` file in ``views_dir`` in lexical order.

    Views must be idempotent (use ``CREATE OR REPLACE VIEW``). Run AFTER
    ``apply_migrations`` so the underlying tables exist.

    Args:
        con: Open DuckDB connection to apply views against.
        views_dir: Directory to scan. Defaults to the package's ``views/``.

    Returns:
        List of view filenames applied, in application order.
    """
    vdir = views_dir or VIEWS_DIR
    if not vdir.exists():
        return []
    applied: list[str] = []
    for sql_file in sorted(vdir.glob("*.sql")):
        con.execute(sql_file.read_text(encoding="utf-8"))
        applied.append(sql_file.name)
    return applied


if __name__ == "__main__":
    con = duckdb.connect(":memory:")
    names = apply_migrations(con)
    views = apply_views(con)
    tables = [row[0] for row in con.execute("SHOW TABLES").fetchall()]
    print(f"Applied migrations: {names}")
    print(f"Applied views: {views}")
    print(f"Tables: {tables}")
