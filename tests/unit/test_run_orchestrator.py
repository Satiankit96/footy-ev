"""Unit tests for the top-level run.py orchestrator.

Confirms each subcommand exists with the expected signature. Does not
actually execute backtests (those are integration-tier and slow).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import typer

_RUN_PY = Path(__file__).resolve().parents[2] / "run.py"


def _load_run_module():
    spec = importlib.util.spec_from_file_location("run_orchestrator", _RUN_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_py_exists():
    assert _RUN_PY.exists(), f"run.py not found at {_RUN_PY}"


def test_app_is_typer():
    mod = _load_run_module()
    assert isinstance(mod.app, typer.Typer)


def test_subcommands_registered():
    """canonical / dashboard / status / paper-trade / paper-status must all
    be registered Typer commands."""
    mod = _load_run_module()
    names = {info.name for info in mod.app.registered_commands}
    assert {
        "canonical",
        "dashboard",
        "status",
        "paper-trade",
        "paper-status",
    }.issubset(names), names


def test_canonical_signature():
    mod = _load_run_module()
    sig = inspect.signature(mod.canonical)
    params = sig.parameters
    assert "league" in params
    assert "db_path" in params


def test_dashboard_signature():
    mod = _load_run_module()
    sig = inspect.signature(mod.dashboard)
    # dashboard takes no required positional args
    assert all(p.default is not inspect.Parameter.empty for p in sig.parameters.values())


def test_status_signature():
    mod = _load_run_module()
    sig = inspect.signature(mod.status)
    assert "db_path" in sig.parameters


def test_no_business_logic_imported_inline():
    """run.py should not redefine model fitting or eval logic; it imports."""
    src = _RUN_PY.read_text(encoding="utf-8")
    # Must delegate, not redefine
    assert "from footy_ev.backtest.walkforward import" in src
    assert "from footy_ev.eval.cli import evaluate_run" in src
    # Sanity: keep the file lean. Bumped from 290 -> 320 in Phase 3 step 5c to
    # accommodate cycle/loop/bootstrap/status subcommands; pipeline-state logic
    # was moved to footy_ev.runtime.status to preserve the thin-dispatcher rule.
    assert len(src.splitlines()) <= 320, "run.py should stay thin"


def test_dashboard_path_is_absolute_and_relative_to_script(monkeypatch):
    """`run.py dashboard` must launch with an absolute path so it works from
    any cwd, and that path must be `<run.py dir>/dashboard/app.py`."""
    mod = _load_run_module()

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, *args, **kwargs):  # noqa: ANN001 - shim
        captured["cmd"] = list(cmd)

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod.dashboard()

    cmd = captured["cmd"]
    # ["uv", "run", "streamlit", "run", "<absolute>/dashboard/app.py"]
    assert cmd[:4] == ["uv", "run", "streamlit", "run"]
    resolved = Path(cmd[4])
    assert resolved.is_absolute(), f"dashboard path must be absolute, got {resolved}"
    assert resolved == (_RUN_PY.parent / "dashboard" / "app.py").resolve()
