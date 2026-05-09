"""Long-running runtimes that drive the orchestration graph.

Phase 3 step 1 ships paper_trader (single-pass + continuous polling).
"""

from footy_ev.runtime.paper_trader import PaperTraderConfig, run_forever, run_once

__all__ = ["PaperTraderConfig", "run_forever", "run_once"]
