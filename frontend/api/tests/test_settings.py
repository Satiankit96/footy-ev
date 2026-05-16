"""Operator settings endpoint tests.

Key invariants:
  - GET /settings returns 200 with defaults when no file exists.
  - PUT /settings persists values and returns 200.
  - Invalid Literal values produce 422.
  - Round-trip PUT then GET returns identical values.
  - Auth is required on both endpoints.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_VALID_SETTINGS = {
    "theme": "dark",
    "density": "compact",
    "default_page_size": 25,
    "default_time_range_days": 14,
}


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


# ── GET defaults ───────────────────────────────────────────────────────────────


def test_get_settings_defaults(tmp_path: Path) -> None:
    """GET /settings with no persisted file returns 200 with valid default values."""
    with patch(
        "footy_ev_api.adapters.settings._settings_path", return_value=tmp_path / "settings.json"
    ):
        c = _client()
        _auth(c)
        r = c.get("/api/v1/settings")

    assert r.status_code == 200
    body = r.json()
    assert "settings" in body
    s = body["settings"]
    assert s["theme"] in ("dark", "light", "system")
    assert s["density"] in ("comfortable", "compact")
    assert s["default_page_size"] in (25, 50, 100)
    assert s["default_time_range_days"] in (7, 14, 30, 90)


# ── PUT updates theme ──────────────────────────────────────────────────────────


def test_put_settings_theme(tmp_path: Path) -> None:
    """PUT /settings with theme=dark returns 200 with updated theme."""
    with patch(
        "footy_ev_api.adapters.settings._settings_path", return_value=tmp_path / "settings.json"
    ):
        c = _client()
        _auth(c)
        r = c.put("/api/v1/settings", json=_VALID_SETTINGS)

    assert r.status_code == 200
    body = r.json()
    assert body["settings"]["theme"] == "dark"


# ── PUT invalid theme → 422 ───────────────────────────────────────────────────


def test_put_settings_invalid_theme() -> None:
    """PUT /settings with theme=invalid returns 422 Unprocessable Entity."""
    c = _client()
    _auth(c)
    payload = dict(_VALID_SETTINGS)
    payload["theme"] = "invalid"
    r = c.put("/api/v1/settings", json=payload)
    assert r.status_code == 422


# ── PUT invalid density → 422 ─────────────────────────────────────────────────


def test_put_settings_invalid_density() -> None:
    """PUT /settings with density=mega returns 422 Unprocessable Entity."""
    c = _client()
    _auth(c)
    payload = dict(_VALID_SETTINGS)
    payload["density"] = "mega"
    r = c.put("/api/v1/settings", json=payload)
    assert r.status_code == 422


# ── Round-trip ─────────────────────────────────────────────────────────────────


def test_settings_roundtrip(tmp_path: Path) -> None:
    """PUT then GET returns the same persisted values."""
    settings_file = tmp_path / "settings.json"
    with patch("footy_ev_api.adapters.settings._settings_path", return_value=settings_file):
        c = _client()
        _auth(c)
        put_r = c.put("/api/v1/settings", json=_VALID_SETTINGS)
        assert put_r.status_code == 200
        get_r = c.get("/api/v1/settings")

    assert get_r.status_code == 200
    assert get_r.json()["settings"] == put_r.json()["settings"]
    assert get_r.json()["settings"]["theme"] == "dark"
    assert get_r.json()["settings"]["density"] == "compact"
    assert get_r.json()["settings"]["default_page_size"] == 25
    assert get_r.json()["settings"]["default_time_range_days"] == 14


# ── Auth guard ─────────────────────────────────────────────────────────────────


def test_settings_requires_auth() -> None:
    """GET and PUT /settings both return 401 without authentication."""
    c = _client()
    for url, method in [
        ("/api/v1/settings", "GET"),
        ("/api/v1/settings", "PUT"),
    ]:
        r = c.request(method, url, json=_VALID_SETTINGS)
        assert r.status_code == 401, f"{method} {url} should require auth"
