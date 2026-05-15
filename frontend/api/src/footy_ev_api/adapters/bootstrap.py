"""In-process bootstrap adapter.

Wraps scripts/bootstrap_kalshi_aliases.py functions for use by the
API's JobManager. Falls back gracefully when the main project or
bootstrap dependencies are missing.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from footy_ev_api.errors import AppError
from footy_ev_api.jobs.manager import Job
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent


def _get_db_path() -> Path:
    settings = Settings()
    return Path(settings.warehouse_path)


def _ensure_bootstrap_importable() -> None:
    """Add scripts/ to sys.path so bootstrap_kalshi_aliases is importable."""
    scripts_dir = str(_PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def run_bootstrap(
    job: Job,
    broadcast: Callable[[dict[str, Any]], None],
    *,
    mode: str = "live",
    create_fixtures: bool = True,
    fixture_path: str | None = None,
) -> None:
    """Run bootstrap in-process, emitting progress events."""

    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _emit(step: str, message: str, percent: int = 0) -> None:
        event = {
            "type": "progress",
            "timestamp": _now_iso(),
            "payload": {"job_id": job.job_id, "step": step, "message": message, "percent": percent},
        }
        job.progress.append(event)
        broadcast(event)

    try:
        _ensure_bootstrap_importable()
        import duckdb
        from footy_ev.db import apply_migrations, apply_views

        db_path = _get_db_path()
        if not db_path.parent.exists():
            raise AppError("BOOTSTRAP_ERROR", f"Warehouse not found at {db_path}", 500)

        _emit("init", "Connecting to warehouse", 5)
        con = duckdb.connect(str(db_path))
        apply_migrations(con)
        apply_views(con)

        from bootstrap_kalshi_aliases import (  # type: ignore[import-not-found]
            _load_canonical_teams,
            _load_existing_kalshi_aliases,
            _resolve_event,
        )

        _emit("load_teams", "Loading canonical team names", 10)
        canonical = _load_canonical_teams(con)
        if not canonical:
            raise AppError("BOOTSTRAP_ERROR", "team_aliases is empty. Run ingestion first.", 500)

        existing = _load_existing_kalshi_aliases(con)
        _emit("load_aliases", f"Found {len(existing)} existing aliases", 15)

        events: list[dict[str, Any]] = []
        if mode == "live":
            _emit("fetch_events", "Fetching events from Kalshi API", 20)
            from footy_ev.venues.kalshi import KalshiClient

            client = KalshiClient.from_env()
            resp = client.list_events(series_ticker="KXEPLTOTAL")
            events_models = resp.payload if isinstance(resp.payload, list) else []
            events = [{"event_ticker": e.event_ticker, "title": e.title} for e in events_models]
        elif mode == "fixture" and fixture_path:
            _emit("load_fixture", f"Loading fixture file: {fixture_path}", 20)
            import json

            fp = Path(fixture_path)
            if not fp.exists():
                raise AppError("BOOTSTRAP_ERROR", f"Fixture file not found: {fixture_path}", 400)
            raw = json.loads(fp.read_text())
            events = raw.get("events", raw) if isinstance(raw, dict) else raw
        else:
            raise AppError("BOOTSTRAP_ERROR", f"Invalid mode: {mode}", 400)

        _emit("process", f"Processing {len(events)} events", 30)

        auto_resolved = 0
        fixture_auto_created = 0
        needs_review = 0
        error_count = 0
        errors: list[dict[str, str]] = []
        now_utc = datetime.now(tz=UTC)

        for i, event in enumerate(events):
            ticker = str(event.get("event_ticker", ""))
            title = str(event.get("title", ""))
            if not ticker:
                continue
            if ticker in existing:
                continue

            percent = 30 + int(60 * (i + 1) / max(len(events), 1))
            try:
                resolution = _resolve_event(
                    con, ticker, title, canonical, 75, now_utc, create_fixtures, dry_run=False
                )
                if resolution is None:
                    needs_review += 1
                    _emit("event", f"Needs review: {ticker}", percent)
                else:
                    fixture_id, resolved_by, confidence, detail = resolution
                    from bootstrap_kalshi_aliases import (
                        _insert_alias,
                    )

                    _insert_alias(con, ticker, fixture_id, confidence, resolved_by, dry_run=False)
                    if detail == "synthetic":
                        fixture_auto_created += 1
                    auto_resolved += 1
                    _emit("event", f"Resolved: {ticker} -> {fixture_id}", percent)
            except Exception as exc:
                error_count += 1
                errors.append({"event_ticker": ticker, "error": str(exc)})
                _emit("event", f"Error: {ticker}: {exc}", percent)

        result = {
            "auto_resolved_count": auto_resolved,
            "fixture_auto_created_count": fixture_auto_created,
            "needs_review_count": needs_review,
            "error_count": error_count,
            "errors": errors,
            "total_events": len(events),
        }
        job.progress.append({"type": "result", "payload": result})

        broadcast(
            {
                "type": "completed",
                "timestamp": _now_iso(),
                "payload": {"job_id": job.job_id, **result},
            }
        )

        con.close()

    except AppError:
        raise
    except ImportError as exc:
        raise AppError(
            "BOOTSTRAP_UNAVAILABLE",
            f"Bootstrap dependencies not available: {exc}",
            503,
        ) from exc
    except Exception as exc:
        broadcast(
            {
                "type": "failed",
                "timestamp": _now_iso(),
                "payload": {"job_id": job.job_id, "error": str(exc)},
            }
        )
        raise


def preview_bootstrap(*, mode: str = "live", fixture_path: str | None = None) -> dict[str, Any]:
    """Dry-run bootstrap: returns what would happen without writing."""
    try:
        _ensure_bootstrap_importable()
        import duckdb
        from footy_ev.db import apply_migrations, apply_views

        db_path = _get_db_path()
        con = duckdb.connect(str(db_path), read_only=True)
        apply_migrations(con)
        apply_views(con)

        from bootstrap_kalshi_aliases import (
            _load_canonical_teams,
            _load_existing_kalshi_aliases,
            _resolve_event,
        )

        canonical = _load_canonical_teams(con)
        existing = _load_existing_kalshi_aliases(con)

        events: list[dict[str, Any]] = []
        if mode == "live":
            from footy_ev.venues.kalshi import KalshiClient

            client = KalshiClient.from_env()
            resp = client.list_events(series_ticker="KXEPLTOTAL")
            events_models = resp.payload if isinstance(resp.payload, list) else []
            events = [{"event_ticker": e.event_ticker, "title": e.title} for e in events_models]
        elif mode == "fixture" and fixture_path:
            import json

            fp = Path(fixture_path)
            if not fp.exists():
                raise AppError("BOOTSTRAP_ERROR", f"Fixture file not found: {fixture_path}", 400)
            raw = json.loads(fp.read_text())
            events = raw.get("events", raw) if isinstance(raw, dict) else raw

        now_utc = datetime.now(tz=UTC)
        would_resolve = 0
        would_create_fixture = 0
        would_skip = 0
        already_mapped = 0

        for event in events:
            ticker = str(event.get("event_ticker", ""))
            title = str(event.get("title", ""))
            if not ticker:
                continue
            if ticker in existing:
                already_mapped += 1
                continue
            resolution = _resolve_event(
                con, ticker, title, canonical, 75, now_utc, True, dry_run=True
            )
            if resolution is None:
                would_skip += 1
            else:
                _fid, _by, _conf, detail = resolution
                if detail == "synthetic":
                    would_create_fixture += 1
                would_resolve += 1

        con.close()
        return {
            "total_events": len(events),
            "already_mapped": already_mapped,
            "would_resolve": would_resolve,
            "would_create_fixture": would_create_fixture,
            "would_skip": would_skip,
        }
    except AppError:
        raise
    except ImportError as exc:
        raise AppError(
            "BOOTSTRAP_UNAVAILABLE", f"Bootstrap dependencies not available: {exc}", 503
        ) from exc
    except Exception as exc:
        raise AppError("BOOTSTRAP_ERROR", str(exc), 500) from exc
