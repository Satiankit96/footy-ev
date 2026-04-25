"""Column registry for football-data.co.uk CSVs.

Source columns change across seasons (bookmakers come and go, new markets appear).
This registry is the single source of truth for which columns we know how to parse
and what their canonical Python/SQL names are. Anything observed in a CSV but NOT
listed here is treated as "unknown" and flows into the ``extras`` MAP column plus
a row in ``schema_drift_log`` (see loader.py) so drift never silently loses data.

Pinnacle note: CLAUDE.md bans Pinnacle as a LIVE odds API source (public access
shut down July 2025). Historical Pinnacle columns sitting in these static CSVs
(PSH/PSD/PSA, PAHH/PAHA, P>2.5/P<2.5) are ALLOWED — past sharp-book prices are a
valuable training feature. The ban is live API pulling only, not historical data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["int", "float", "str", "date", "time"]


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """Metadata for one source column."""

    source_name: str  # header string in the raw CSV (e.g. "FTHG", "B365>2.5")
    canonical_name: str  # snake_case Python field / SQL column (e.g. "fthg", "b365_over_25")
    kind: Kind
    required: bool = False
    notes: str = ""


REGISTRY: tuple[ColumnSpec, ...] = (
    # --- Core match (required every season) ---
    ColumnSpec("Div", "div", "str", required=True),
    ColumnSpec("Date", "match_date", "date", required=True),
    ColumnSpec("Time", "match_time", "time"),
    ColumnSpec("HomeTeam", "home_team", "str", required=True),
    ColumnSpec("AwayTeam", "away_team", "str", required=True),
    ColumnSpec("FTHG", "fthg", "int", required=True),
    ColumnSpec("FTAG", "ftag", "int", required=True),
    ColumnSpec("FTR", "ftr", "str", required=True),
    ColumnSpec("HTHG", "hthg", "int"),
    ColumnSpec("HTAG", "htag", "int"),
    ColumnSpec("HTR", "htr", "str"),
    ColumnSpec("Referee", "referee", "str"),
    # --- Match stats (oldest seasons frequently missing) ---
    ColumnSpec("HS", "hs", "int", notes="home shots total"),
    ColumnSpec(
        "AS", "as_", "int", notes="away shots total; AS is a SQL reserved word so canonical is as_"
    ),
    ColumnSpec("HST", "hst", "int", notes="home shots on target"),
    ColumnSpec("AST", "ast", "int", notes="away shots on target"),
    ColumnSpec("HF", "hf", "int", notes="home fouls committed"),
    ColumnSpec("AF", "af", "int"),
    ColumnSpec("HC", "hc", "int", notes="home corners"),
    ColumnSpec("AC", "ac", "int"),
    ColumnSpec("HY", "hy", "int", notes="home yellow cards"),
    ColumnSpec("AY", "ay", "int"),
    ColumnSpec("HR", "hr", "int", notes="home red cards"),
    ColumnSpec("AR", "ar", "int"),
    # --- 1X2 decimal odds per bookmaker ---
    ColumnSpec("B365H", "b365h", "float"),
    ColumnSpec("B365D", "b365d", "float"),
    ColumnSpec("B365A", "b365a", "float"),
    ColumnSpec("BWH", "bwh", "float"),
    ColumnSpec("BWD", "bwd", "float"),
    ColumnSpec("BWA", "bwa", "float"),
    ColumnSpec("IWH", "iwh", "float"),
    ColumnSpec("IWD", "iwd", "float"),
    ColumnSpec("IWA", "iwa", "float"),
    ColumnSpec(
        "PSH", "psh", "float", notes="Pinnacle historical only; live API banned per CLAUDE.md"
    ),
    ColumnSpec("PSD", "psd", "float"),
    ColumnSpec("PSA", "psa", "float"),
    ColumnSpec("WHH", "whh", "float"),
    ColumnSpec("WHD", "whd", "float"),
    ColumnSpec("WHA", "wha", "float"),
    ColumnSpec("VCH", "vch", "float"),
    ColumnSpec("VCD", "vcd", "float"),
    ColumnSpec("VCA", "vca", "float"),
    ColumnSpec("MaxH", "maxh", "float"),
    ColumnSpec("MaxD", "maxd", "float"),
    ColumnSpec("MaxA", "maxa", "float"),
    ColumnSpec("AvgH", "avgh", "float"),
    ColumnSpec("AvgD", "avgd", "float"),
    ColumnSpec("AvgA", "avga", "float"),
    ColumnSpec("BFEH", "bfeh", "float", notes="Betfair Exchange back odds; newer seasons only"),
    ColumnSpec("BFED", "bfed", "float"),
    ColumnSpec("BFEA", "bfea", "float"),
    # --- Over/Under 2.5 goals ---
    ColumnSpec("B365>2.5", "b365_over_25", "float"),
    ColumnSpec("B365<2.5", "b365_under_25", "float"),
    ColumnSpec("P>2.5", "p_over_25", "float"),
    ColumnSpec("P<2.5", "p_under_25", "float"),
    ColumnSpec("Max>2.5", "max_over_25", "float"),
    ColumnSpec("Max<2.5", "max_under_25", "float"),
    ColumnSpec("Avg>2.5", "avg_over_25", "float"),
    ColumnSpec("Avg<2.5", "avg_under_25", "float"),
    # --- Asian handicap ---
    ColumnSpec("AHh", "ah_line", "float", notes="handicap line applied to home team"),
    ColumnSpec("B365AHH", "b365_ah_home", "float"),
    ColumnSpec("B365AHA", "b365_ah_away", "float"),
    ColumnSpec("PAHH", "p_ah_home", "float"),
    ColumnSpec("PAHA", "p_ah_away", "float"),
    # =====================================================================
    # Migration 002 promotions: closing-odds families + pre-match AH aggregates.
    # =====================================================================
    # --- 1X2 closing odds (9 books × 3 = 27) ---
    ColumnSpec("B365CH", "b365ch", "float", notes="Bet365 1X2 closing"),
    ColumnSpec("B365CD", "b365cd", "float"),
    ColumnSpec("B365CA", "b365ca", "float"),
    ColumnSpec("BWCH", "bwch", "float"),
    ColumnSpec("BWCD", "bwcd", "float"),
    ColumnSpec("BWCA", "bwca", "float"),
    ColumnSpec("WHCH", "whch", "float"),
    ColumnSpec("WHCD", "whcd", "float"),
    ColumnSpec("WHCA", "whca", "float"),
    ColumnSpec(
        "PSCH",
        "psch",
        "float",
        notes=(
            "HIGH VALUE: 14-season Pinnacle closing-odds dataset, primary CLV "
            "training label. Per CLAUDE.md exception: historical Pinnacle data "
            "allowed (live Pinnacle API banned)."
        ),
    ),
    ColumnSpec("PSCD", "pscd", "float"),
    ColumnSpec("PSCA", "psca", "float"),
    ColumnSpec("IWCH", "iwch", "float"),
    ColumnSpec("IWCD", "iwcd", "float"),
    ColumnSpec("IWCA", "iwca", "float"),
    ColumnSpec("VCCH", "vcch", "float"),
    ColumnSpec("VCCD", "vccd", "float"),
    ColumnSpec("VCCA", "vcca", "float"),
    ColumnSpec("MaxCH", "maxch", "float"),
    ColumnSpec("MaxCD", "maxcd", "float"),
    ColumnSpec("MaxCA", "maxca", "float"),
    ColumnSpec("AvgCH", "avgch", "float"),
    ColumnSpec("AvgCD", "avgcd", "float"),
    ColumnSpec("AvgCA", "avgca", "float"),
    ColumnSpec("BFECH", "bfech", "float"),
    ColumnSpec("BFECD", "bfecd", "float"),
    ColumnSpec("BFECA", "bfeca", "float"),
    # --- Over/Under 2.5 closing (5 books × 2 = 10) ---
    ColumnSpec("B365C>2.5", "b365c_over_25", "float"),
    ColumnSpec("B365C<2.5", "b365c_under_25", "float"),
    ColumnSpec("MaxC>2.5", "maxc_over_25", "float"),
    ColumnSpec("MaxC<2.5", "maxc_under_25", "float"),
    ColumnSpec("AvgC>2.5", "avgc_over_25", "float"),
    ColumnSpec("AvgC<2.5", "avgc_under_25", "float"),
    ColumnSpec(
        "PC>2.5",
        "pc_over_25",
        "float",
        notes="Pinnacle closing O/U; historical-only per CLAUDE.md.",
    ),
    ColumnSpec("PC<2.5", "pc_under_25", "float"),
    ColumnSpec("BFEC>2.5", "bfec_over_25", "float"),
    ColumnSpec("BFEC<2.5", "bfec_under_25", "float"),
    # --- Asian handicap closing + pre-match aggregates (11 + 4 = 15) ---
    ColumnSpec("AHCh", "ahc_line", "float", notes="closing AH handicap line"),
    ColumnSpec("B365CAHH", "b365c_ah_home", "float"),
    ColumnSpec("B365CAHA", "b365c_ah_away", "float"),
    ColumnSpec("MaxCAHH", "maxc_ah_home", "float"),
    ColumnSpec("MaxCAHA", "maxc_ah_away", "float"),
    ColumnSpec("AvgCAHH", "avgc_ah_home", "float"),
    ColumnSpec("AvgCAHA", "avgc_ah_away", "float"),
    ColumnSpec(
        "PCAHH",
        "pc_ah_home",
        "float",
        notes="Pinnacle closing AH; historical-only per CLAUDE.md.",
    ),
    ColumnSpec("PCAHA", "pc_ah_away", "float"),
    ColumnSpec("BFECAHH", "bfec_ah_home", "float"),
    ColumnSpec("BFECAHA", "bfec_ah_away", "float"),
    ColumnSpec("MaxAHH", "max_ah_home", "float"),
    ColumnSpec("MaxAHA", "max_ah_away", "float"),
    ColumnSpec("AvgAHH", "avg_ah_home", "float"),
    ColumnSpec("AvgAHA", "avg_ah_away", "float"),
    # =====================================================================
    # DEFERRED — promote on second appearance (per "promote on second appearance" rule):
    #
    #   - 1xBet (1XB{H,D,A} open + 1XBC{H,D,A} close): first seen 2024-25 EPL.
    #   - Betfair non-Exchange (BF{H,D,A} open + BFC{H,D,A} close): first seen 2024-25.
    #     (Distinct from the registered BFE* Betfair Exchange columns.)
    #   - Brand-new in 2025-26 EPL: BFD{H,D,A,C*}, BMGM{H,D,A,C*}, BV{H,D,A,C*},
    #     CL{H,D,A,C*}, plus LBC{H,D,A} (Ladbrokes closing returning?).
    #
    # Revisit migration 003 once 2026-27 EPL starts and these columns persist into a
    # second season. Until promoted, these flow through the extras MAP and create
    # rows in schema_drift_log on every ingestion (visible to the operator).
    # =====================================================================
)


BY_SOURCE: dict[str, ColumnSpec] = {c.source_name: c for c in REGISTRY}
BY_CANONICAL: dict[str, ColumnSpec] = {c.canonical_name: c for c in REGISTRY}
SOURCE_NAMES: frozenset[str] = frozenset(c.source_name for c in REGISTRY)
REQUIRED_SOURCE_NAMES: frozenset[str] = frozenset(c.source_name for c in REGISTRY if c.required)


if __name__ == "__main__":
    print(f"{len(REGISTRY)} columns registered ({len(REQUIRED_SOURCE_NAMES)} required)")
    print(f"required source names: {sorted(REQUIRED_SOURCE_NAMES)}")
