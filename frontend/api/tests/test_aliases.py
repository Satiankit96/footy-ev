"""Alias endpoint tests with mocked DuckDB adapter."""

from __future__ import annotations

import os
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


_MOCK_ALIAS = {
    "event_ticker": "KXEPLTOTAL-26MAY14TEST",
    "fixture_id": "epl_2026-05-14_ARS_MCI",
    "confidence": 0.95,
    "resolved_by": "fuzzy_match",
    "resolved_at": "2026-05-14T12:00:00+00:00",
    "status": "active",
}


@patch("footy_ev_api.routers.aliases.list_aliases")
def test_list_aliases(mock_list: Any) -> None:
    mock_list.return_value = {"aliases": [_MOCK_ALIAS], "total": 1}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/aliases")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["aliases"]) == 1
    assert body["aliases"][0]["event_ticker"] == "KXEPLTOTAL-26MAY14TEST"


@patch("footy_ev_api.routers.aliases.list_aliases")
def test_list_aliases_with_status_filter(mock_list: Any) -> None:
    mock_list.return_value = {"aliases": [], "total": 0}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/aliases?status=retired")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    mock_list.assert_called_once_with(status="retired", limit=100, offset=0)


@patch("footy_ev_api.routers.aliases.get_alias")
def test_get_alias(mock_get: Any) -> None:
    mock_get.return_value = _MOCK_ALIAS
    c = _client()
    _auth(c)
    r = c.get("/api/v1/aliases/KXEPLTOTAL-26MAY14TEST")
    assert r.status_code == 200
    assert r.json()["fixture_id"] == "epl_2026-05-14_ARS_MCI"


@patch("footy_ev_api.routers.aliases.get_alias")
def test_get_alias_not_found(mock_get: Any) -> None:
    mock_get.return_value = None
    c = _client()
    _auth(c)
    r = c.get("/api/v1/aliases/NONEXISTENT")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ALIAS_NOT_FOUND"


@patch("footy_ev_api.routers.aliases.get_conflicts")
def test_get_conflicts(mock_conflicts: Any) -> None:
    mock_conflicts.return_value = [
        {"fixture_id": "epl_2026-05-14_ARS_MCI", "alias_count": 2, "tickers": ["T1", "T2"]},
    ]
    c = _client()
    _auth(c)
    r = c.get("/api/v1/aliases/conflicts")
    assert r.status_code == 200
    body = r.json()
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["alias_count"] == 2


@patch("footy_ev_api.routers.aliases.create_alias")
def test_create_alias(mock_create: Any) -> None:
    mock_create.return_value = _MOCK_ALIAS
    c = _client()
    _auth(c)
    r = c.post(
        "/api/v1/aliases",
        json={
            "event_ticker": "KXEPLTOTAL-26MAY14TEST",
            "fixture_id": "epl_2026-05-14_ARS_MCI",
            "confidence": 0.95,
        },
    )
    assert r.status_code == 200
    assert r.json()["event_ticker"] == "KXEPLTOTAL-26MAY14TEST"


@patch("footy_ev_api.routers.aliases.retire_alias")
def test_retire_alias(mock_retire: Any) -> None:
    mock_retire.return_value = {
        "event_ticker": "KXEPLTOTAL-26MAY14TEST",
        "status": "retired",
        "retired_at": "2026-05-14T12:30:00+00:00",
    }
    c = _client()
    _auth(c)
    r = c.post("/api/v1/aliases/KXEPLTOTAL-26MAY14TEST/retire")
    assert r.status_code == 200
    assert r.json()["status"] == "retired"


def test_aliases_requires_auth() -> None:
    c = _client()
    r = c.get("/api/v1/aliases")
    assert r.status_code == 401
