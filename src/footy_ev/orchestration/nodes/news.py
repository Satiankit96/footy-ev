"""News node stub.

Phase 3 step 1 ships a no-op. Real Ollama integration is a future step
(BLUE_MAP s1.4). The signature is locked now so the graph topology
doesn't change when the real implementation lands.
"""

from __future__ import annotations

from typing import Any

from footy_ev.orchestration.state import BettingState


def news_node(state: BettingState) -> dict[str, Any]:
    return {"news_deltas": []}
