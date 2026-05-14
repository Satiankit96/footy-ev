"""Pipeline endpoint tests."""

from __future__ import annotations

import os
import time

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


def test_start_cycle():
    c = _client()
    _auth(c)
    r = c.post("/api/v1/pipeline/cycle")
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["status"] in ("queued", "running")


def test_start_cycle_conflict():
    c = _client()
    _auth(c)
    r1 = c.post("/api/v1/pipeline/cycle")
    assert r1.status_code == 200
    # immediately try again while first is still running
    r2 = c.post("/api/v1/pipeline/cycle")
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "CONFLICT"


def test_pipeline_status():
    c = _client()
    _auth(c)
    r = c.get("/api/v1/pipeline/status")
    assert r.status_code == 200
    body = r.json()
    assert "last_cycle_at" in body
    assert "circuit_breaker" in body
    assert "loop" in body
    assert "freshness" in body
    assert body["loop"]["active"] is False


def test_loop_start_stop():
    c = _client()
    _auth(c)
    r = c.post("/api/v1/pipeline/loop/start", json={"interval_min": 60})
    assert r.status_code == 200
    assert r.json()["interval_min"] == 60

    r2 = c.get("/api/v1/pipeline/loop")
    assert r2.status_code == 200
    assert r2.json()["active"] is True

    r3 = c.post("/api/v1/pipeline/loop/stop")
    assert r3.status_code == 200
    time.sleep(0.2)

    r4 = c.get("/api/v1/pipeline/loop")
    assert r4.status_code == 200


def test_loop_start_conflict():
    c = _client()
    _auth(c)
    c.post("/api/v1/pipeline/loop/start", json={"interval_min": 60})
    r = c.post("/api/v1/pipeline/loop/start", json={"interval_min": 30})
    assert r.status_code == 409


def test_freshness_shape():
    c = _client()
    _auth(c)
    r = c.get("/api/v1/pipeline/freshness")
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    first = next(iter(body.values()))
    assert "source" in first
    assert "threshold_seconds" in first
    assert "status" in first


def test_jobs_list():
    c = _client()
    _auth(c)
    c.post("/api/v1/pipeline/cycle")
    time.sleep(3)
    r = c.get("/api/v1/pipeline/jobs")
    assert r.status_code == 200
    assert len(r.json()["jobs"]) >= 1


def test_job_detail():
    c = _client()
    _auth(c)
    r = c.post("/api/v1/pipeline/cycle")
    job_id = r.json()["job_id"]
    time.sleep(3)
    r2 = c.get(f"/api/v1/pipeline/jobs/{job_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["job_id"] == job_id
    assert len(body["progress"]) > 0
