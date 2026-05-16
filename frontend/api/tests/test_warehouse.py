"""Warehouse explorer endpoint tests.

All DB-touching adapter functions are mocked so the test suite runs without
a real warehouse file. Key invariants tested:
  - Happy-path responses match adapter output
  - Unknown query name → 400
  - Auth required on every endpoint
  - Players returns empty list with a note
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_MOCK_TABLES = {
    "tables": [
        {"name": "paper_bets", "row_count": 42, "last_write": "2026-05-15T10:00:00"},
        {"name": "raw_match_results", "row_count": 380, "last_write": None},
    ]
}

_MOCK_TEAMS = {
    "teams": [
        {"team_id": "arsenal", "name": "Arsenal", "league": "EPL", "fixture_count": 38},
        {"team_id": "chelsea", "name": None, "league": "EPL", "fixture_count": 38},
    ],
    "total": 2,
}

_MOCK_TEAM_DETAIL = {
    "team_id": "arsenal",
    "name": "Arsenal",
    "league": "EPL",
    "form": [
        {
            "fixture_id": "EPL|2025-2026|arsenal|chelsea|2026-05-10",
            "date": "2026-05-10",
            "opponent_id": "chelsea",
            "home_away": "home",
            "score": "2 - 1",
            "result": "W",
            "home_xg": "1.8",
            "away_xg": "0.9",
        }
    ],
}

_MOCK_SNAPSHOTS = {
    "snapshots": [
        {
            "fixture_id": "EPL|2025-2026|arsenal|chelsea|2026-05-20",
            "venue": "betfair",
            "market": "match_result",
            "selection": "Home",
            "odds_decimal": 2.1,
            "received_at": "2026-05-20T09:00:00",
        }
    ],
    "total": 1,
}

_MOCK_QUERY_RESULT = {
    "query_name": "top_fixtures_by_bet_count",
    "columns": ["fixture_id", "bet_count", "total_staked_gbp", "avg_edge_pct"],
    "rows": [["EPL|2025-2026|arsenal|chelsea|2026-05-20", 3, 75.00, 0.052]],
    "row_count": 1,
}


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


# ── Tables ─────────────────────────────────────────────────────────────────────


@patch("footy_ev_api.routers.warehouse.list_tables")
def test_list_tables(mock_lt: Any) -> None:
    mock_lt.return_value = dict(_MOCK_TABLES)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/tables")
    assert r.status_code == 200
    body = r.json()
    assert len(body["tables"]) == 2
    assert body["tables"][0]["name"] == "paper_bets"
    assert body["tables"][0]["row_count"] == 42
    assert body["tables"][0]["last_write"] == "2026-05-15T10:00:00"
    assert body["tables"][1]["last_write"] is None


# ── Teams ──────────────────────────────────────────────────────────────────────


@patch("footy_ev_api.routers.warehouse.list_teams")
def test_list_teams(mock_lt: Any) -> None:
    mock_lt.return_value = dict(_MOCK_TEAMS)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/teams")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["teams"][0]["team_id"] == "arsenal"
    assert body["teams"][0]["name"] == "Arsenal"


@patch("footy_ev_api.routers.warehouse.list_teams")
def test_list_teams_league_filter_forwarded(mock_lt: Any) -> None:
    mock_lt.return_value = dict(_MOCK_TEAMS)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/teams?league=EPL")
    assert r.status_code == 200
    mock_lt.assert_called_once_with(league="EPL")


@patch("footy_ev_api.routers.warehouse.get_team")
def test_get_team_detail(mock_gt: Any) -> None:
    mock_gt.return_value = dict(_MOCK_TEAM_DETAIL)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/teams/arsenal")
    assert r.status_code == 200
    body = r.json()
    assert body["team_id"] == "arsenal"
    assert body["league"] == "EPL"
    assert len(body["form"]) == 1
    assert body["form"][0]["result"] == "W"


@patch("footy_ev_api.routers.warehouse.get_team")
def test_get_team_not_found(mock_gt: Any) -> None:
    mock_gt.return_value = None
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/teams/nonexistent")
    assert r.status_code == 404


# ── Players ────────────────────────────────────────────────────────────────────


def test_list_players_empty() -> None:
    """Players endpoint always returns an empty list with an explanatory note."""
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/players")
    assert r.status_code == 200
    body = r.json()
    assert body["players"] == []
    assert "note" in body
    assert len(body["note"]) > 0


# ── Snapshots ──────────────────────────────────────────────────────────────────


@patch("footy_ev_api.routers.warehouse.list_snapshots")
def test_list_snapshots(mock_ls: Any) -> None:
    mock_ls.return_value = dict(_MOCK_SNAPSHOTS)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/odds-snapshots")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["snapshots"][0]["venue"] == "betfair"
    assert body["snapshots"][0]["odds_decimal"] == pytest.approx(2.1, abs=1e-9)


# ── Canned queries ─────────────────────────────────────────────────────────────


@patch("footy_ev_api.routers.warehouse.run_canned_query")
def test_run_canned_query(mock_rq: Any) -> None:
    mock_rq.return_value = dict(_MOCK_QUERY_RESULT)
    c = _client()
    _auth(c)
    r = c.post(
        "/api/v1/warehouse/query",
        json={"query_name": "top_fixtures_by_bet_count", "params": {"limit": 5}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["query_name"] == "top_fixtures_by_bet_count"
    assert body["row_count"] == 1
    assert body["columns"] == ["fixture_id", "bet_count", "total_staked_gbp", "avg_edge_pct"]


def test_unknown_query_name_rejected() -> None:
    """POST /warehouse/query with an unknown name must return 400 without touching the DB."""
    c = _client()
    _auth(c)
    r = c.post(
        "/api/v1/warehouse/query",
        json={"query_name": "DROP TABLE paper_bets; --", "params": {}},
    )
    assert r.status_code == 400
    body = r.json()
    err = body.get("error", {})
    assert "allowlist" in err.get("message", "").lower() or "unknown" in err.get("code", "").lower()


def test_query_names_endpoint() -> None:
    """GET /warehouse/query/names returns a non-empty sorted list of strings."""
    c = _client()
    _auth(c)
    r = c.get("/api/v1/warehouse/query/names")
    assert r.status_code == 200
    names = r.json()
    assert isinstance(names, list)
    assert len(names) >= 5  # we created 5 sql files
    assert names == sorted(names)


# ── Auth guard ─────────────────────────────────────────────────────────────────


def test_warehouse_requires_auth() -> None:
    c = _client()
    for url, method in [
        ("/api/v1/warehouse/tables", "GET"),
        ("/api/v1/warehouse/teams", "GET"),
        ("/api/v1/warehouse/players", "GET"),
        ("/api/v1/warehouse/odds-snapshots", "GET"),
        ("/api/v1/warehouse/query", "POST"),
    ]:
        r = c.request(method, url)
        assert r.status_code == 401, f"{method} {url} should require auth"
