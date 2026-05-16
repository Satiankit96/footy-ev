"""JSON file persistence adapter for operator settings."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from footy_ev_api.settings import Settings

_log = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "theme": "system",
    "density": "comfortable",
    "default_page_size": 50,
    "default_time_range_days": 30,
}


def _settings_path() -> Path:
    """Return the path to the operator settings JSON file."""
    return Path(Settings().warehouse_path).parent / "operator_settings.json"


def get_settings() -> dict[str, Any]:
    """Read operator settings from disk.

    Returns:
        Persisted settings dict, or defaults when the file is missing or corrupt.
    """
    path = _settings_path()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        return data
    except FileNotFoundError:
        return dict(_DEFAULTS)
    except Exception:  # noqa: BLE001
        _log.warning("Failed to read settings from %s — returning defaults", path)
        return dict(_DEFAULTS)


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Atomically write operator settings to disk.

    Args:
        data: Settings dict to persist.

    Returns:
        The saved settings dict.
    """
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(data, tmp, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except Exception:  # noqa: BLE001
        _log.warning("Failed to save settings to %s", path)
    return data
