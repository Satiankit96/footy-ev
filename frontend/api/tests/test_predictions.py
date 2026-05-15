"""Predictions endpoint tests with mocked DuckDB adapter."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.main import create_app

TEST_TOKEN = "test-operator-token-12345"

_MOCK_PREDICTION = {
    "prediction_id": "abc123def456abc123def456abc12345",
    "fixture_id": "EPL|2025-2026|arsenal|manchester_city|2026-05-14",
    "market": "ou_2.5",
    "selection": "over",
    "p_raw": 0.5412,
    "p_calibrated": 0.5412,
    "sigma_p": 0.05,
    "model_version": "xgb_ou25_v1",
    "features_hash": "deadbeef12345678",
    "as_of": "2026-05-14T10:00:00+00:00",
    "generated_at": "2026-05-14T10:00:01+00:00",
    "run_id": "api_run_abc123",
}

_MOCK_FEATURES = {
    "prediction_id": "abc123def456abc123def456abc12345",
    "fixture_id": "EPL|2025-2026|arsenal|manchester_city|2026-05-14",
    "features_hash": "deadbeef12345678",
    "features": [
        {
            "name": "home_xg_for_5",
            "value": 1.82,
            "description": "Home team average xG scored per match, last 5 matches",
        },
        {
            "name": "away_xg_for_5",
            "value": 1.54,
            "description": "Away team average xG scored per match, last 5 matches",
        },
    ],
    "error": None,
}


def _client() -> TestClient:
    os.environ["UI_OPERATOR_TOKEN"] = TEST_TOKEN
    JobManager.reset()
    return TestClient(create_app())


def _auth(c: TestClient) -> None:
    c.post("/api/v1/auth/login", json={"token": TEST_TOKEN})


@patch("footy_ev_api.routers.predictions.list_predictions")
def test_list_predictions(mock_list: Any) -> None:
    mock_list.return_value = {"predictions": [_MOCK_PREDICTION], "total": 1}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/predictions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["predictions"][0]["market"] == "ou_2.5"
    assert body["predictions"][0]["p_calibrated"] == 0.5412


@patch("footy_ev_api.routers.predictions.list_predictions")
def test_list_predictions_filters(mock_list: Any) -> None:
    mock_list.return_value = {"predictions": [], "total": 0}
    c = _client()
    _auth(c)
    r = c.get("/api/v1/predictions?fixture_id=EPL|2025&model_version=xgb_ou25_v1&market=ou_2.5")
    assert r.status_code == 200
    mock_list.assert_called_once_with(
        fixture_id="EPL|2025",
        model_version="xgb_ou25_v1",
        market="ou_2.5",
        date_from=None,
        date_to=None,
        limit=50,
        offset=0,
    )


@patch("footy_ev_api.routers.predictions.get_prediction")
def test_prediction_detail(mock_get: Any) -> None:
    mock_get.return_value = dict(_MOCK_PREDICTION)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/predictions/abc123def456abc123def456abc12345")
    assert r.status_code == 200
    body = r.json()
    assert body["prediction_id"] == "abc123def456abc123def456abc12345"
    assert body["sigma_p"] == 0.05


@patch("footy_ev_api.routers.predictions.get_prediction")
def test_prediction_detail_not_found(mock_get: Any) -> None:
    mock_get.return_value = None
    c = _client()
    _auth(c)
    r = c.get("/api/v1/predictions/nonexistent")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PREDICTION_NOT_FOUND"


@patch("footy_ev_api.routers.predictions.get_prediction_features")
def test_prediction_features(mock_feats: Any) -> None:
    mock_feats.return_value = dict(_MOCK_FEATURES)
    c = _client()
    _auth(c)
    r = c.get("/api/v1/predictions/abc123def456abc123def456abc12345/features")
    assert r.status_code == 200
    body = r.json()
    assert body["features_hash"] == "deadbeef12345678"
    assert len(body["features"]) == 2
    assert body["features"][0]["name"] == "home_xg_for_5"
    assert body["features"][0]["value"] == 1.82


@patch("footy_ev_api.routers.predictions.get_prediction_features")
def test_prediction_features_not_found(mock_feats: Any) -> None:
    mock_feats.return_value = None
    c = _client()
    _auth(c)
    r = c.get("/api/v1/predictions/nonexistent/features")
    assert r.status_code == 404


@patch("footy_ev_api.routers.predictions.run_predictions")
def test_prediction_run(mock_run: Any) -> None:
    c = _client()
    _auth(c)
    r = c.post("/api/v1/predictions/run", json={"fixture_ids": ["EPL|fix1"]})
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["status"] in ("queued", "running", "completed")


def test_predictions_requires_auth() -> None:
    c = _client()
    r = c.get("/api/v1/predictions")
    assert r.status_code == 401
