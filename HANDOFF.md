# HANDOFF — footy-ev

**Phase 3 step 5c complete (2026-05-12). Project ~88% complete.**

The remainder is operational paper-trading runs, not code. The pipeline is end-to-end functional against Kalshi demo. Phase 4 (live trading) is gated on PROJECT_INSTRUCTIONS §3 conditions and is not part of this codebase yet.

## What just landed in 5c

- **Migration 012** seeds 20 EPL 3-letter codes into `team_aliases (source='kalshi_code')`.
- **Migration 013** adds a physical `synthetic_fixtures` table; `v_fixtures_epl` now `UNION ALL`s warehouse fixtures with Kalshi-derived synthetic rows so downstream consumers see one fixtures stream.
- **`scripts/bootstrap_kalshi_aliases.py`** rewritten end-to-end:
  - Ticker parse (`KXEPLTOTAL-{YY}{MON}{DD}{AWAY3}{HOME3}`) is the PRIMARY signal.
  - Title parse (`"X at Y: Total Goals"` and `"X vs Y - Totals"` variants) is the fallback.
  - Date-aware future-only fixture matching with ±1d window and `status != 'final'`.
  - Synthetic fixture creation (`KXFIX-<event_ticker>`) gated to `[today-1d, today+14d]`.
  - `--no-create-fixtures` flag to disable synthetic creation.
- **`run.py`** unified orchestrator: `cycle` (default), `loop`, `bootstrap`, `status`, plus legacy `canonical`/`paper-trade`/`paper-status`/`dashboard` for `make.ps1` compatibility. Refuses `LIVE_TRADING=true` until Phase 4.
- **`src/footy_ev/runtime/status.py`** — pipeline-state reporter (warehouse-only). Used by `run.py status` and `run.py cycle`.
- **`README.md`** rewritten as operator handbook.
- **22 new tests** (ticker parser × 6, title parser × 5, fixture creation × 5, migration 012 × 2, run smoke × 4). Suite: 312 passing.

## Daily operation

```powershell
uv run python run.py bootstrap          # weekly: refresh Kalshi aliases
uv run python run.py                    # one cycle
uv run python run.py loop --interval-min 15
uv run python run.py status             # warehouse-only state table
uv run python run.py dashboard          # Streamlit UI
```

## Known caveats carried into operation

- **Synthetic fixtures use noon-UTC kickoff.** Real kickoff times will arrive when a current-season fixture source is wired (football-data.co.uk CSV or api-football).
- **Calibration disabled.** `p_calibrated = p_raw`. Isotonic degraded Brier across walk-forward — revisit as a structural decision.
- **Zero-bid markets dropped at DEBUG.** Liquidity-history retention via `is_tradeable=False` column is on the deferred list.
- **Demo only.** `KALSHI_API_BASE_URL` is the switch to production once the §3 conditions hold.

## Phase 4 gating (no code yet)

Per PROJECT_INSTRUCTIONS §3, live trading requires BOTH:
1. Positive CLV on 1000+ paper bets over 60+ consecutive days against Kalshi close.
2. Disposable bankroll.

`run.py` currently refuses `LIVE_TRADING=true` unconditionally; Phase 4 will add the actual gate logic.

## Where to read more

- README.md — operator handbook (setup, daily ops, dashboard)
- BLUE_MAP.md — architecture spec
- PROJECT_INSTRUCTIONS.md — rules, banned paths, rigor
- CLAUDE.md — Claude Code always-on context
- SETUP_GUIDE.md — Kalshi onboarding
