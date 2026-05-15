"""Predictions endpoints — list, detail, features, run."""

from __future__ import annotations

import functools

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.predictions import (
    get_prediction,
    get_prediction_features,
    list_predictions,
    run_predictions,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.errors import AppError
from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.schemas.predictions import (
    PredictionFeatureItem,
    PredictionFeaturesResponse,
    PredictionListResponse,
    PredictionResponse,
    PredictionRunRequest,
    PredictionRunResponse,
)

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("", response_model=PredictionListResponse)
async def prediction_list(
    _operator: str = Depends(get_current_operator),
    fixture_id: str | None = Query(default=None),
    model_version: str | None = Query(default=None),
    market: str | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PredictionListResponse:
    """Paginated predictions list with composable filters."""
    data = list_predictions(
        fixture_id=fixture_id,
        model_version=model_version,
        market=market,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PredictionListResponse(
        predictions=[PredictionResponse(**p) for p in data["predictions"]],
        total=data["total"],
    )


@router.post("/run", response_model=PredictionRunResponse)
async def prediction_run(
    body: PredictionRunRequest,
    _operator: str = Depends(get_current_operator),
) -> PredictionRunResponse:
    """Score fixtures in-process and write results to model_predictions."""
    mgr = JobManager()
    run_fn = functools.partial(
        run_predictions,
        fixture_ids=body.fixture_ids,
    )
    try:
        job = mgr.start_job("predictions", run_fn)
    except ValueError as exc:
        raise AppError("CONFLICT", str(exc), 409) from exc
    return PredictionRunResponse(job_id=job.job_id, status=job.status.value)


@router.get("/{prediction_id}/features", response_model=PredictionFeaturesResponse)
async def prediction_features(
    prediction_id: str,
    _operator: str = Depends(get_current_operator),
) -> PredictionFeaturesResponse:
    """Return the named feature vector that produced this prediction."""
    data = get_prediction_features(prediction_id)
    if data is None:
        raise AppError(
            "PREDICTION_NOT_FOUND",
            f"Prediction {prediction_id} not found",
            404,
        )
    return PredictionFeaturesResponse(
        prediction_id=data["prediction_id"],
        fixture_id=data["fixture_id"],
        features_hash=data["features_hash"],
        features=[PredictionFeatureItem(**f) for f in data["features"]],
        error=data.get("error"),
    )


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def prediction_detail(
    prediction_id: str,
    _operator: str = Depends(get_current_operator),
) -> PredictionResponse:
    """Single prediction detail."""
    data = get_prediction(prediction_id)
    if data is None:
        raise AppError(
            "PREDICTION_NOT_FOUND",
            f"Prediction {prediction_id} not found",
            404,
        )
    return PredictionResponse(**data)
