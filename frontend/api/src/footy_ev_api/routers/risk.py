"""Risk router — /api/v1/risk/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from footy_ev_api.adapters.risk import (
    get_bankroll,
    get_exposure,
)
from footy_ev_api.adapters.risk import (
    kelly_preview as adapter_kelly_preview,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.schemas.risk import (
    BankrollResponse,
    ExposureResponse,
    KellyPreviewRequest,
    KellyPreviewResponse,
)

router = APIRouter(tags=["risk"])


@router.get(
    "/risk/exposure",
    response_model=ExposureResponse,
    dependencies=[Depends(get_current_operator)],
)
def route_exposure() -> ExposureResponse:
    """Current open exposure: per-fixture breakdown and totals."""
    return ExposureResponse(**get_exposure())


@router.get(
    "/risk/bankroll",
    response_model=BankrollResponse,
    dependencies=[Depends(get_current_operator)],
)
def route_bankroll() -> BankrollResponse:
    """Current bankroll, peak, drawdown from peak, and sparkline history."""
    return BankrollResponse(**get_bankroll())


@router.post(
    "/risk/kelly-preview",
    response_model=KellyPreviewResponse,
    dependencies=[Depends(get_current_operator)],
)
def route_kelly_preview(body: KellyPreviewRequest) -> KellyPreviewResponse:
    """Pure Kelly stake calculator — zero side effects, zero DB writes."""
    result = adapter_kelly_preview(
        p_hat=body.p_hat,
        sigma_p=body.sigma_p,
        odds=body.odds,
        base_fraction=body.base_fraction,
        uncertainty_k=body.uncertainty_k,
        per_bet_cap_pct=body.per_bet_cap_pct,
        recent_clv_pct=body.recent_clv_pct,
        bankroll=body.bankroll,
    )
    return KellyPreviewResponse(**result)
