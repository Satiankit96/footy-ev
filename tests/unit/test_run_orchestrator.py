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
    """canonical / dashboard / status must all be registered Typer commands."""
    mod = _load_run_module()
    names = {info.name for info in mod.app.registered_commands}
    assert {"canonical", "dashboard", "status"}.issubset(names), names


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
    # Sanity: keep the file lean
    assert len(src.splitlines()) <= 200, "run.py should stay thin (~100 lines)"
