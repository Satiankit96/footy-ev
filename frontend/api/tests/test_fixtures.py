"""Fixtures endpoint tests with mocked DuckDB adapter."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_MOCK_FIXTURE = {
    "fixture_id": "EPL|2025-2026|arsenal|manchester_city|2026-05-14",
    "league": "EPL",
    "season": "2025-2026",
    "home_team_id": "arsenal",
    "away_team_id": "manchester_city",
    "home_team_raw": "Arsenal",
    "away_team_raw": "Man City",
    "match_date": "2026-05-14",
    "kickoff_utc": "2026-05-14T15:00:00",
    "home_score_ft": None,
    "away_score_ft": None,
    "result_ft": None,
    "home_xg": None,
    "away_xg": None,
    "status": "scheduled",
    "alias_count": 1,
}

_MOCK_FIXTURE_DETAIL = {
    **_MOCK_FIXTURE,
    "aliases": [
        {
            "event_ticker": "KXEPLTOTAL-26MAY14ARSMCI",
            "confidence": 0.92,
            "resolved_by": "fuzzy_match",
            "resolved_at": "2026-05-14T10:00:00+00:00",
        }
    ],
    "prediction_count": 0,
    "bet_count": 0,
}


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


@patch("footy_ev_api.routers.fixtures.list_fixtures")
def test_list_fixtures(mock_list: Any) -> None:
    mock_list.return_value = {"fixtures": [_MOCK_FIXTURE], "total": 1}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/fixtures")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["fixtures"]) == 1
    assert body["fixtures"][0]["league"] == "EPL"


@patch("footy_ev_api.routers.fixtures.list_fixtures")
def test_list_fixtures_with_filters(mock_list: Any) -> None:
    mock_list.return_value = {"fixtures": [], "total": 0}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/fixtures?status=scheduled&league=EPL&season=2025-2026")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    mock_list.assert_called_once_with(
        status="scheduled",
        league="EPL",
        season="2025-2026",
        date_from=None,
        date_to=None,
        limit=50,
        offset=0,
    )


@patch("footy_ev_api.routers.fixtures.list_fixtures")
def test_list_fixtures_pagination(mock_list: Any) -> None:
    mock_list.return_value = {"fixtures": [], "total": 200}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/fixtures?limit=25&offset=50")
    assert r.status_code == 200
    mock_list.assert_called_once_with(
        status=None,
        league=None,
        season=None,
        date_from=None,
        date_to=None,
        limit=25,
        offset=50,
    )


@patch("footy_ev_api.routers.fixtures.get_fixture")
def test_fixture_detail(mock_get: Any) -> None:
    mock_get.return_value = dict(_MOCK_FIXTURE_DETAIL)
    c = _client()
    _auth(c)
    fid = "EPL|2025-2026|arsenal|manchester_city|2026-05-14"
    r = c.get(f"/api/v1/fixtures/{fid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "scheduled"
    assert len(body["aliases"]) == 1
    assert body["aliases"][0]["event_ticker"] == "KXEPLTOTAL-26MAY14ARSMCI"
    assert body["prediction_count"] == 0
    assert body["bet_count"] == 0


@patch("footy_ev_api.routers.fixtures.get_fixture")
def test_fixture_detail_not_found(mock_get: Any) -> None:
    mock_get.return_value = None
    c = _client()
    _auth(c)
    r = c.get("/api/v1/fixtures/NONEXISTENT")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FIXTURE_NOT_FOUND"


@patch("footy_ev_api.routers.fixtures.list_upcoming")
def test_fixtures_upcoming(mock_upcoming: Any) -> None:
    mock_upcoming.return_value = {"fixtures": [_MOCK_FIXTURE], "total": 1}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/fixtures/upcoming?days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    mock_upcoming.assert_called_once_with(days=7)


def test_fixtures_requires_auth() -> None:
    c = _client()
    r = c.get("/api/v1/fixtures")
    assert r.status_code == 401
