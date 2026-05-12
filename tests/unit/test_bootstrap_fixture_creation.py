"""Unit tests for synthetic-fixture creation in bootstrap_kalshi_aliases.

Spec gates:
  - kickoff_date in [today-1d, today+14d] only
  - fixture_id prefix: 'KXFIX-<event_ticker>'
  - Idempotent via INSERT OR IGNORE on PK
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from bootstrap_kalshi_aliases import (  # type: ignore[import-not-found] # noqa: E402
    _create_synthetic_fixture,
    _resolve_event,
)

from footy_ev.db import apply_migrations, apply_views  # noqa: E402


@pytest.fixture
def warehouse(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    apply_migrations(con)
    apply_views(con)
    return con


def test_creates_synthetic_when_no_warehouse_fixture(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    today = datetime.now(tz=UTC).date()
    kickoff = today + timedelta(days=3)
    # Build a ticker reflecting that kickoff date for end-to-end realism.
    ticker = f"KXEPLTOTAL-{kickoff.strftime('%y%b%d').upper()}WHULEE"
    # No raw_match_results seeded → no warehouse fixture exists.
    canonical: dict[str, str] = {}  # title fallback not needed when ticker resolves
    resolution = _resolve_event(
        warehouse,
        ticker=ticker,
        title="West Ham at Leeds United: Total Goals",
        canonical=canonical,
        threshold=75,
        now_utc=datetime.now(tz=UTC),
        create_fixtures=True,
        dry_run=False,
    )
    assert resolution is not None
    fixture_id, _, _, detail = resolution
    assert detail == "synthetic"
    assert fixture_id == f"KXFIX-{ticker}"
    # Synthetic row landed in warehouse
    n = warehouse.execute(
        "SELECT COUNT(*) FROM synthetic_fixtures WHERE fixture_id = ?", [fixture_id]
    ).fetchone()[0]
    assert n == 1


def test_skips_past_events_outside_window(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    today = datetime.now(tz=UTC).date()
    kickoff = today - timedelta(days=10)
    ticker = f"KXEPLTOTAL-{kickoff.strftime('%y%b%d').upper()}WHULEE"
    resolution = _resolve_event(
        warehouse,
        ticker=ticker,
        title="ignored",
        canonical={},
        threshold=75,
        now_utc=datetime.now(tz=UTC),
        create_fixtures=True,
        dry_run=False,
    )
    assert resolution is None
    n = warehouse.execute("SELECT COUNT(*) FROM synthetic_fixtures").fetchone()[0]
    assert n == 0


def test_skips_far_future_events_outside_window(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    today = datetime.now(tz=UTC).date()
    kickoff = today + timedelta(days=30)
    ticker = f"KXEPLTOTAL-{kickoff.strftime('%y%b%d').upper()}WHULEE"
    resolution = _resolve_event(
        warehouse,
        ticker=ticker,
        title="ignored",
        canonical={},
        threshold=75,
        now_utc=datetime.now(tz=UTC),
        create_fixtures=True,
        dry_run=False,
    )
    assert resolution is None


def test_synthetic_creation_is_idempotent(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    kickoff = date(2099, 6, 15)  # far-future but we bypass gating via direct call
    fid1 = _create_synthetic_fixture(
        warehouse, "KXEPLTOTAL-99JUN15WHULEE", "leeds", "west_ham", kickoff, dry_run=False
    )
    fid2 = _create_synthetic_fixture(
        warehouse, "KXEPLTOTAL-99JUN15WHULEE", "leeds", "west_ham", kickoff, dry_run=False
    )
    assert fid1 == fid2
    n = warehouse.execute(
        "SELECT COUNT(*) FROM synthetic_fixtures WHERE fixture_id = ?", [fid1]
    ).fetchone()[0]
    assert n == 1, "INSERT OR IGNORE must produce a single row across repeats"


def test_fixture_id_prefix(warehouse: duckdb.DuckDBPyConnection) -> None:
    fid = _create_synthetic_fixture(
        warehouse,
        "KXEPLTOTAL-99JUN15WHULEE",
        "leeds",
        "west_ham",
        date(2099, 6, 15),
        dry_run=False,
    )
    assert fid.startswith("KXFIX-")
    assert fid == "KXFIX-KXEPLTOTAL-99JUN15WHULEE"
