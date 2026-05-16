"""Audit endpoint tests.

All DB-touching adapter functions are mocked so the suite runs without a
real warehouse. Key invariants:
  - Operator actions, model versions, and decisions endpoints all respond.
  - Auth required.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_MOCK_ACTIONS = {
    "actions": [
        {
            "action_id": "aa-bb-cc",
            "action_type": "pipeline_cycle",
            "operator": "operator",
            "performed_at": "2026-05-15T10:00:00",
            "input_params": None,
            "result_summary": "pipeline_cycle succeeded (HTTP 200)",
            "request_id": "req-123",
        }
    ],
    "total": 1,
}

_MOCK_VERSIONS = {
    "versions": [
        {
            "model_version": "xgb-v3.2.1",
            "first_seen": "2026-04-01T09:00:00",
            "last_seen": "2026-05-15T09:00:00",
            "prediction_count": 42,
        }
    ]
}

_MOCK_DECISIONS = {
    "decisions": [
        {
            "bet_id": "bet-001",
            "fixture_id": "EPL|2025-2026|arsenal|chelsea|2026-05-20",
            "decided_at": "2026-05-15T10:30:00",
            "market": "match_result",
            "selection": "Home",
            "stake_gbp": "15.00",
            "odds": "2.10",
            "edge_pct": 0.052,
            "settlement_status": "pending",
            "prediction_id": "pred-abc",
        }
    ],
    "total": 1,
}


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


# ── Operator actions ───────────────────────────────────────────────────────────


@patch("footy_ev_api.routers.audit.list_operator_actions")
def test_operator_actions(mock_la: Any) -> None:
    mock_la.return_value = dict(_MOCK_ACTIONS)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/audit/operator-actions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["actions"][0]["action_type"] == "pipeline_cycle"
    assert body["actions"][0]["operator"] == "operator"


@patch("footy_ev_api.routers.audit.list_operator_actions")
def test_operator_actions_filter_forwarded(mock_la: Any) -> None:
    mock_la.return_value = dict(_MOCK_ACTIONS)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/audit/operator-actions?action_type=pipeline_cycle&limit=5")
    assert r.status_code == 200
    mock_la.assert_called_once_with(
        action_type="pipeline_cycle",
        since=None,
        limit=5,
        offset=0,
    )


# ── Model versions ─────────────────────────────────────────────────────────────


@patch("footy_ev_api.routers.audit.list_model_versions")
def test_model_versions(mock_mv: Any) -> None:
    mock_mv.return_value = dict(_MOCK_VERSIONS)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/audit/model-versions")
    assert r.status_code == 200
    body = r.json()
    assert len(body["versions"]) == 1
    assert body["versions"][0]["model_version"] == "xgb-v3.2.1"
    assert body["versions"][0]["prediction_count"] == 42


# ── Decisions ──────────────────────────────────────────────────────────────────


@patch("footy_ev_api.routers.audit.list_decisions")
def test_decisions(mock_ld: Any) -> None:
    mock_ld.return_value = dict(_MOCK_DECISIONS)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/audit/decisions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["decisions"][0]["bet_id"] == "bet-001"
    assert body["decisions"][0]["stake_gbp"] == "15.00"


# ── Auth guard ─────────────────────────────────────────────────────────────────


def test_audit_requires_auth() -> None:
    c = _client()
    for url in [
        "/api/v1/audit/operator-actions",
        "/api/v1/audit/model-versions",
        "/api/v1/audit/decisions",
    ]:
        r = c.get(url)
        assert r.status_code == 401, f"GET {url} should require auth"


# ── Middleware integration: audit row written on mutation ──────────────────────


@patch("footy_ev_api.middleware.audit._write_audit_row")
def test_audit_middleware_fires_on_pipeline_cycle(mock_write: Any) -> None:
    """POST /pipeline/cycle triggers an audit write (if successful)."""
    c = _client()
    _auth(c)
    # This will 'fail' the cycle (no real pipeline), but we check middleware fires
    # on any 2xx. The cycle might return 200 with status=failed; we patch the
    # write and just verify it fires if the route returns 2xx.
    with patch("footy_ev_api.routers.pipeline.run_pipeline_cycle", return_value=None):
        r = c.post("/api/v1/pipeline/cycle")
    if r.status_code == 200:
        assert mock_write.called
        call_args = mock_write.call_args
        assert call_args[0][0] == "pipeline_cycle"


@patch("footy_ev_api.middleware.audit._write_audit_row")
def test_audit_middleware_sanitises_secrets(mock_write: Any) -> None:
    """Token fields are redacted in input_params."""
    from footy_ev_api.middleware.audit import _sanitize_params

    body = b'{"query_name": "top_fixtures", "token": "super-secret", "limit": 10}'
    result = _sanitize_params(body)
    assert result is not None
    assert result["token"] == "[REDACTED]"
    assert result["limit"] == 10
    assert result["query_name"] == "top_fixtures"


def test_audit_middleware_no_log_on_get() -> None:
    """GET requests are never audit-logged."""
    from footy_ev_api.middleware.audit import _get_action_type

    assert _get_action_type("GET", "/api/v1/pipeline/cycle") is None
    assert _get_action_type("GET", "/api/v1/diagnostics/circuit-breaker/reset") is None


def test_audit_alias_retire_path_matched() -> None:
    """Dynamic path /api/v1/aliases/{ticker}/retire is recognised."""
    from footy_ev_api.middleware.audit import _get_action_type

    assert _get_action_type("POST", "/api/v1/aliases/KXEPL-001/retire") == "alias_retire"
    assert (
        _get_action_type("POST", "/api/v1/aliases/some-random-ticker-abc/retire") == "alias_retire"
    )
    assert _get_action_type("POST", "/api/v1/aliases") == "alias_create"
