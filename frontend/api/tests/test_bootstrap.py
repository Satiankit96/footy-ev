"""Bootstrap endpoint tests with mocked adapters."""

from __future__ import annotations

import os
import threading
import time
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


@patch("footy_ev_api.routers.bootstrap.preview_bootstrap")
def test_bootstrap_preview(mock_preview: Any) -> None:
    mock_preview.return_value = {
        "total_events": 42,
        "already_mapped": 30,
        "would_resolve": 8,
        "would_create_fixture": 2,
        "would_skip": 2,
    }
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bootstrap/preview")
    assert r.status_code == 200
    body = r.json()
    assert body["total_events"] == 42
    assert body["would_resolve"] == 8
    assert body["would_create_fixture"] == 2


@patch("footy_ev_api.routers.bootstrap.run_bootstrap")
def test_bootstrap_run(mock_run: Any) -> None:
    c = _client()
    _auth(c)
    r = c.post("/api/v1/bootstrap/run", json={"mode": "live"})
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["status"] in ("queued", "running", "completed")


def test_bootstrap_run_conflict() -> None:
    hold = threading.Event()

    def _blocking_run(job: Any, broadcast: Any, **kwargs: Any) -> None:
        hold.wait(timeout=5)

    c = _client()
    _auth(c)
    with patch("footy_ev_api.routers.bootstrap.run_bootstrap", side_effect=_blocking_run):
        r1 = c.post("/api/v1/bootstrap/run", json={"mode": "live"})
        assert r1.status_code == 200
        time.sleep(0.3)
        r2 = c.post("/api/v1/bootstrap/run", json={"mode": "live"})
        assert r2.status_code == 409
        hold.set()


def test_bootstrap_jobs_empty() -> None:
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bootstrap/jobs")
    assert r.status_code == 200
    assert r.json()["jobs"] == []


@patch("footy_ev_api.routers.bootstrap.run_bootstrap")
def test_bootstrap_job_detail(mock_run: Any) -> None:
    c = _client()
    _auth(c)
    r = c.post("/api/v1/bootstrap/run", json={"mode": "live"})
    job_id = r.json()["job_id"]
    r2 = c.get(f"/api/v1/bootstrap/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id


def test_bootstrap_job_not_found() -> None:
    c = _client()
    _auth(c)
    r = c.get("/api/v1/bootstrap/jobs/nonexistent")
    assert r.status_code == 404


def test_bootstrap_requires_auth() -> None:
    c = _client()
    r = c.post("/api/v1/bootstrap/run", json={"mode": "live"})
    assert r.status_code == 401
