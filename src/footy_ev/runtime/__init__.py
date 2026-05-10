"""Long-running runtimes that drive the orchestration graph.

Phase 3 step 1 ships paper_trader (single-pass + continuous polling).
Phase 3 step 2 adds model_loader (production scorer wired into analyst node).
"""

from footy_ev.runtime.model_loader import (
    NoProductionModelError,
    detect_production_run_id,
    load_production_scorer,
)
from footy_ev.runtime.paper_trader import PaperTraderConfig, run_forever, run_once

__all__ = [
    "NoProductionModelError",
    "PaperTraderConfig",
    "detect_production_run_id",
    "load_production_scorer",
    "run_forever",
    "run_once",
]
