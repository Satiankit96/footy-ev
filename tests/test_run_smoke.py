"""Smoke tests for the run.py unified orchestrator.

These tests do not exercise the LangGraph pipeline end-to-end; they only verify
that the dispatcher loads, --help works, status executes against a warehouse,
unknown commands fail with a clear error, and LIVE_TRADING=true is refused.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUN_PY = _REPO_ROOT / "run.py"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(_RUN_PY), *args],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(_REPO_ROOT),
        timeout=60,
    )


def test_help_lists_new_subcommands() -> None:
    res = _run("--help")
    assert res.returncode == 0, res.stderr
    out = res.stdout
    for cmd in ("cycle", "loop", "bootstrap", "status", "dashboard"):
        assert cmd in out, f"--help missing subcommand: {cmd}\n{out}"


def test_status_runs_against_warehouse(tmp_path: Path) -> None:
    db_path = tmp_path / "smoke.duckdb"
    res = _run("status", "--db-path", str(db_path))
    assert res.returncode == 0, res.stderr
    assert "footy-ev pipeline state" in res.stdout
    assert "Active venue" in res.stdout


def test_invalid_subcommand_exits_nonzero() -> None:
    res = _run("not-a-real-command")
    assert res.returncode != 0
    # typer surfaces "No such command" in stderr
    assert "No such command" in (res.stderr + res.stdout)


def test_live_trading_is_refused() -> None:
    res = _run("cycle", env={"LIVE_TRADING": "true"})
    assert res.returncode != 0
    assert "LIVE_TRADING" in res.stdout
    assert "Phase 4" in res.stdout
