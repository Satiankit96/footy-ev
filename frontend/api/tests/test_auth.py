"""Auth endpoint tests."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    return TestClient(create_app())


def test_auth_login_success():
    c = _client()
    r = c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "session" in r.cookies


def test_auth_login_failure():
    c = _client()
    r = c.post("/api/v1/auth/login", json={"token": "wrong-token"})
    assert r.status_code == 401
    assert r.json()["ok"] is False
    assert "session" not in r.cookies


def test_auth_me_with_session():
    c = _client()
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["operator"] == "operator"
    assert body["session_started_at"] is not None


def test_auth_me_without_session():
    c = _client()
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_auth_logout():
    c = _client()
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})
    r = c.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_shell_requires_auth():
    c = _client()
    r = c.get("/api/v1/shell")
    assert r.status_code == 401


def test_shell_returns_venue():
    os.environ["KALSHI_API_BASE_URL"] = "https://demo-api.kalshi.co/trade-api/v2"
    c = _client()
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})
    r = c.get("/api/v1/shell")
    assert r.status_code == 200
    body = r.json()
    assert body["venue"]["name"] == "kalshi"
    assert body["venue"]["is_demo"] is True
    assert body["circuit_breaker"]["state"] == "ok"


def test_health_no_auth_required():
    c = _client()
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
