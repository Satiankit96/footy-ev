"""Stage 2 tests: OpenAPI schema, error envelope, request-id passthrough."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    return TestClient(create_app())


def test_openapi_schema_accessible() -> None:
    c = _client()
    r = c.get("/api/v1/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "paths" in schema
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/auth/logout" in schema["paths"]
    assert "/api/v1/auth/me" in schema["paths"]
    assert "/api/v1/shell" in schema["paths"]


def test_health_response_matches_schema() -> None:
    c = _client()
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["status"], str)
    assert isinstance(body["version"], str)
    assert isinstance(body["uptime_s"], float)
    assert "active_venue" in body


def test_error_envelope_shape() -> None:
    c = _client()
    r = c.post("/api/v1/auth/login", json={"token": "bad"})
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == "INVALID_TOKEN"
    assert isinstance(err["message"], str)
    assert "details" in err
    assert "request_id" in err


def test_request_id_passthrough() -> None:
    c = _client()
    req_id = "test-req-id-abc123"
    r = c.post(
        "/api/v1/auth/login",
        json={"token": "bad"},
        headers={"X-Request-ID": req_id},
    )
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["request_id"] == req_id
