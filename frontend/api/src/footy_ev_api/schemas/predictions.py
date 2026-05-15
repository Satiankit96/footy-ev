"""Prediction endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel


class PredictionResponse(BaseModel):
    """Single model_predictions row."""

    prediction_id: str
    fixture_id: str
    market: str
    selection: str
    p_raw: float
    p_calibrated: float
    sigma_p: float | None = None
    model_version: str
    features_hash: str
    as_of: str | None = None
    generated_at: str | None = None
    run_id: str | None = None


class PredictionListResponse(BaseModel):
    """GET /api/v1/predictions response."""

    predictions: list[PredictionResponse]
    total: int


class PredictionFeatureItem(BaseModel):
    """Single named feature with value and documentation."""

    name: str
    value: float | None = None
    description: str


class PredictionFeaturesResponse(BaseModel):
    """GET /api/v1/predictions/{id}/features response."""

    prediction_id: str
    fixture_id: str
    features_hash: str
    features: list[PredictionFeatureItem]
    error: str | None = None


class PredictionRunRequest(BaseModel):
    """POST /api/v1/predictions/run body."""

    fixture_ids: list[str] | None = None


class PredictionRunResponse(BaseModel):
    """POST /api/v1/predictions/run response."""

    job_id: str
    status: str
