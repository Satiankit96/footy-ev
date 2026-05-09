"""Analyst node — produces calibrated O/U 2.5 probabilities for affected fixtures.

Calls the existing model code; never retrains mid-graph. The model run_id
is passed in via state, so this node is a pure scorer:
  - load XGBoostOU25Fit + XGSkellamFit by run_id (latest fold)
  - build PIT feature row via features.assembler
  - emit ModelProbability per fixture+market+selection
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from footy_ev.orchestration.state import (
    BettingState,
    MarketType,
    ModelProbability,
)

_LOG = logging.getLogger(__name__)


def analyst_node(
    state: BettingState,
    *,
    score_fn: Any | None = None,
) -> dict[str, Any]:
    """Score the fixtures.

    `score_fn` is injected so the runtime can wire in a closure that
    knows how to talk to DuckDB / load fits / build features. Tests pass
    a mock; the runtime passes a real implementation that delegates to
    `runtime.paper_trader._score_fixtures`. The node itself stays pure.
    """
    if state.get("circuit_breaker_tripped"):
        return {"model_probs": []}

    fixtures = state.get("fixtures_to_process", [])
    if not fixtures:
        return {"model_probs": []}

    if score_fn is None:
        # No scorer wired -> empty (graph still flows, just no probs).
        return {"model_probs": []}

    raw: list[dict[str, Any]] = score_fn(fixtures, state.get("as_of"))
    probs: list[ModelProbability] = []
    for r in raw:
        h = hashlib.sha256(
            f"{r['fixture_id']}|{r['market']}|{r['selection']}|{r['p_calibrated']:.6f}".encode()
        ).hexdigest()[:16]
        probs.append(
            ModelProbability(
                fixture_id=r["fixture_id"],
                market=MarketType(r["market"]),
                selection=r["selection"],
                p_raw=float(r.get("p_raw", r["p_calibrated"])),
                p_calibrated=float(r["p_calibrated"]),
                model_version=str(r.get("model_version", "xgb_ou25_v1")),
                features_hash=h,
                uncertainty_se=float(r.get("sigma_p", 0.0) or 0.0),
                run_id=r.get("run_id"),
            )
        )
    return {"model_probs": probs}
