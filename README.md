# footy-ev

Local-first +EV sports betting pipeline targeting European football pre-match markets (Phase 1: EPL OU 2.5).

Goal: sustainable 3–8% yield on turnover, measured by closing-line value (CLV) against Kalshi closing prices. **Paper-trading mode only** — `LIVE_TRADING` is disabled and gated on PROJECT_INSTRUCTIONS §3 conditions.

## Status

**Phase 3 step 5c complete.** Pipeline is end-to-end functional against Kalshi demo. Project ~88% complete; remainder is operational paper-trading runs, not code.

For detailed state see [HANDOFF.md](./HANDOFF.md). Architecture in [BLUE_MAP.md](./BLUE_MAP.md). Project rules in [PROJECT_INSTRUCTIONS.md](./PROJECT_INSTRUCTIONS.md). Always-on Claude Code context in [CLAUDE.md](./CLAUDE.md).

## What's Done

- **Phase 0 — Data:** Historical match data (10+ seasons EPL + 4 other leagues from football-data.co.uk), Understat xG scrape, DuckDB + Parquet warehouse with point-in-time feature views.
- **Phase 1 — Models:** xG-Skellam OU 2.5 baseline (MARGINAL_SIGNAL: mean=+0.0061, p=0.038, all 7 seasons positive). XGBoost stacked on xG-Skellam (best signal: mean=+0.0108, p=0.026). Dixon-Coles 1X2 parked (NO_GO verdict).
- **Phase 2 — Production wiring:** Fractional Kelly with uncertainty haircut and CLV-aware shrinkage, per-bet/per-day/per-fixture caps, audit ledger, paper-bet settlement. Isotonic calibration disabled (Brier degraded in walk-forward; revisit as structural decision).
- **Phase 3 step 1–4 — Orchestration:** LangGraph nodes (scraper, analyst, pricing, risk, execution), DuckDB-backed checkpointing, settlement loop, CLV backfill with multi-source fallback.
- **Phase 3 step 5a–c — Kalshi venue:** RSA-PSS/SHA256 authentication, Pydantic-modeled responses, floor_strike-based OU 2.5 filtering, demo paper trading, ticker-based bootstrap, Kalshi-derived fixture auto-creation.

## What's Deferred

- **Production Kalshi credentials.** Currently demo. Switch after 30+ days of demo paper trading show consistent positive CLV vs Kalshi close.
- **Live trading.** Gated by PROJECT_INSTRUCTIONS §3: positive CLV on 1000+ bets over 60+ days AND disposable bankroll. Both required.
- **Zero-bid snapshot retention.** Currently logged-then-dropped at DEBUG. Add `is_tradeable=False` column for liquidity-history retention when needed.
- **Real kickoff times for Kalshi-derived fixtures.** Noon UTC placeholder. Refine when Kalshi exposes precise kickoff or when a fixtures API is wired.
- **Multi-league expansion** (La Liga, Serie A, Bundesliga, Ligue 1). Phase 2.5.
- **In-play markets.** Phase 5+ per BLUE_MAP §7.4.

## Quick Start

### Prerequisites

- Python 3.12+
- `uv` package manager
- Kalshi demo credentials (Key ID + private RSA PEM at `data/kalshi_private_key.pem`)
- Windows 11 / PowerShell 5.1

### Setup

```powershell
.\make.ps1 install
Copy-Item .env.example .env
# Edit .env:
#   KALSHI_API_KEY_ID=<your-key-id>
#   KALSHI_PRIVATE_KEY_PATH=data/kalshi_private_key.pem
#   KALSHI_API_BASE_URL=https://demo-api.kalshi.co/trade-api/v2
#   KALSHI_COMMISSION_PCT=0.07

uv run python run.py bootstrap
uv run python run.py status
```

### Daily Operation

```powershell
uv run python run.py                            # one cycle
uv run python run.py loop --interval-min 15     # continuous
uv run python run.py dashboard                  # Streamlit UI
uv run python run.py bootstrap                  # refresh aliases (run weekly)
```

### Testing

```powershell
.\make.ps1 test            # fast unit tests
.\make.ps1 test-integration # warehouse-backed integration
.\make.ps1 lint
.\make.ps1 typecheck

$env:FOOTY_EV_KALSHI_DEMO="1"; uv run pytest tests/integration/test_kalshi_live.py -v
```

## Tracking Progress

The dashboard (`run.py dashboard`) surfaces:

- **Active venue + base URL** — confirms demo vs production
- **Production model** — loaded XGBoost run ID, training date
- **Freshness gauges** — time since last Kalshi snapshot, news, prediction
- **Resolved aliases** — count + table of Kalshi events → fixtures
- **Today's activity** — snapshots, predictions, paper bets
- **Rolling CLV** — 100-bet and 500-bet rolling averages (PROJECT_INSTRUCTIONS §6 North Star)
- **Edge after commission** — model edge minus Kalshi fee

For deeper inspection:

```powershell
uv run python -c "import duckdb; con=duckdb.connect('data/footy_ev.duckdb', read_only=True); print(con.execute('SELECT venue, COUNT(*) FROM paper_bets GROUP BY venue').df())"
```

Key tables: `fixtures`, `kalshi_event_aliases`, `kalshi_contract_resolutions`, `odds_snapshots`, `model_predictions`, `paper_bets`.

## Known Limitations

- **Synthetic fixtures from Kalshi events.** `run.py bootstrap` creates fixture rows (prefix `KXFIX-`) when no warehouse fixture matches. When a proper fixtures-ingestion source is wired (football-data.co.uk current-season CSV or api-football), reconcile against real ones. Noon-UTC kickoff is a placeholder.
- **Calibration disabled.** Isotonic monotonically degraded Brier across walk-forward. Currently `p_calibrated = p_raw`. Revisit as a structural decision.
- **Zero-bid handling drops snapshots.** Markets with `yes_bid_dollars == "0.0000"` are logged at DEBUG and skipped. Liquidity-history retention is on the deferred list.
- **Demo only.** Production requires separate registration. `KALSHI_API_BASE_URL` is the switch.

## Project Structure

```
footy-ev/
├── run.py                       ← unified orchestrator (your entry point)
├── README.md                    ← this file
├── CLAUDE.md                    ← Claude Code always-on context
├── HANDOFF.md                   ← latest state for next coding session
├── PROJECT_INSTRUCTIONS.md      ← rules, banned paths, rigor
├── BLUE_MAP.md                  ← architecture spec (do not read §10 unless referenced)
├── SETUP_GUIDE.md               ← installation + Kalshi onboarding
├── make.ps1                     ← PowerShell task runner
├── pyproject.toml
├── .env.example
├── src/footy_ev/
│   ├── venues/                  ← Kalshi client, price translation, resolution
│   ├── orchestration/           ← LangGraph nodes
│   ├── runtime/                 ← paper_trader, settlement, CLV backfill
│   ├── models/                  ← xG-Skellam, XGBoost, Dixon-Coles (parked)
│   ├── db/                      ← schema, migrations
│   └── dashboard/               ← Streamlit app
├── scripts/                     ← bootstrap + ingestion scripts
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── data/                        ← gitignored: Parquet, DuckDB, credentials
└── .claude/                     ← Claude Code config
```

## Critical Discipline

1. **Never set `LIVE_TRADING=true`** until both PROJECT_INSTRUCTIONS §3 conditions hold. `run.py` refuses to start if true.
2. **Never commit `.env` or `data/`** — credentials and market data.
3. **Always run `.\make.ps1 test`** before pushing.
4. **Always check `Active venue`** on the dashboard before assuming demo mode.
5. **Read PROJECT_INSTRUCTIONS §5 (banned paths)** before adding new venues, scraping techniques, or modeling approaches.

## Where to Get Help

- Architecture → [BLUE_MAP.md](./BLUE_MAP.md)
- Rules and rigor → [PROJECT_INSTRUCTIONS.md](./PROJECT_INSTRUCTIONS.md)
- Workflow → [CLAUDE.md](./CLAUDE.md)
- Kalshi setup → [SETUP_GUIDE.md](./SETUP_GUIDE.md)
- Recent changes → `git log --oneline -20`
