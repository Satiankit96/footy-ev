"""Health endpoint test."""

from __future__ import annotations

from fastapi.testclient import TestClient

from footy_ev_api.main import create_app


def test_health():
    client = TestClient(create_app())
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert "uptime_s" in body
