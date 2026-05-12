# Handoff — end of Phase 3 step 3 (Betfair→warehouse fixture alignment)

> Created **2026-05-10** at the close of Phase 3 step 3. Read this in full
> before doing anything else, then `CLAUDE.md`, then `BLUE_MAP.md` only
> for the section a new task touches. Phase 0–2 history is in the prior
> handoffs; Phase 3 step 1 is in the previous HANDOFF.md (committed
> 2026-05-09, last preserved in git history).

---

## 0. Mid-flight note

**5b mid-flight — signing landed, discovery probe ready, shape verification pending operator-side demo run.**
Run `uv run python scripts/probe_kalshi_demo.py` (see `docs/SETUP_GUIDE.md §5b`) and paste the capture file back into chat.

---

## 1. Status banner

We are at the **end of Phase 3 step 3**. The paper-trading vertical
slice now has full fixture alignment:

- **Phase 3 step 2 (complete):** Production XGBoost model wired into the
  analyst node. `model_loader.py` detects the latest completed
  `xgb_ou25_v1` run, deserialises the booster from `xgb_fits`, and
  returns a `score_fn` closure. `run.py paper-trade` accepts
  `--model-run-id` (also `PAPER_TRADER_MODEL_RUN_ID` env).

- **Phase 3 step 3 (complete):** Betfair-to-warehouse fixture alignment.
  Migration 010 adds `betfair_team_aliases`, `betfair_market_aliases`
  (seeded), `betfair_selection_aliases` (seeded), and
  `betfair_event_resolutions`. At runtime, `scraper_node` resolves each
  Betfair event to a warehouse `fixture_id` via a deterministic SQL join;
  unresolved events are dropped; >50% failure trips the circuit breaker.
  Bootstrap script (`scripts/bootstrap_betfair_aliases.py`) populates
  `betfair_team_aliases` via rapidfuzz + interactive review.

**Test suite: 273 unit passed, 1 xfailed (pre-existing migration-002
frozen-header xfail).** Integration test for resolution is gated on
`FOOTY_EV_INTEGRATION_DB=1`.

---

## 2. Key file locations (Phase 3 additions)

| Path | Purpose |
|---|---|
| `src/footy_ev/db/migrations/010_betfair_entity_resolution.sql` | betfair_team_aliases, betfair_market_aliases (seeded), betfair_selection_aliases (seeded), betfair_event_resolutions |
| `src/footy_ev/venues/resolution.py` | resolve_event, resolve_market, resolve_selection, cache_resolution, parse_betfair_event_name, resolve_event_from_meta |
| `src/footy_ev/venues/betfair.py` | Delayed-API client |
| `src/footy_ev/orchestration/state.py` | BettingState — `resolved_fixture_ids` added in step 3 |
| `src/footy_ev/orchestration/nodes/scraper.py` | Resolves each Betfair event; drops unresolved; trips breaker >50% |
| `src/footy_ev/orchestration/nodes/analyst.py` | Uses `resolved_fixture_ids` over `fixtures_to_process` |
| `src/footy_ev/orchestration/graph.py` | Threads `event_meta_map` + `warehouse_con` to scraper |
| `src/footy_ev/runtime/paper_trader.py` | `_resolve_fixtures_and_markets` returns 3-tuple with event_meta_map |
| `src/footy_ev/runtime/model_loader.py` | detect_production_run_id, load_production_scorer, _BOOSTER_CACHE |
| `src/footy_ev/runtime/__init__.py` | Exports NoProductionModelError, detect_production_run_id, load_production_scorer |
| `scripts/bootstrap_betfair_aliases.py` | One-off: rapidfuzz fuzzy match + interactive review → betfair_team_aliases |
| `dashboard/app.py` | Entity Resolution panel + Production Model panel added |
| `dashboard/queries.py` | entity_resolution_summary, entity_resolution_unresolved_events, production_model_info |
| `tests/unit/test_resolution.py` | 18 unit tests for resolution.py |
| `tests/unit/test_scraper_with_resolution.py` | 5 tests: backward compat + resolution scenarios |
| `tests/integration/test_paper_trade_emits_bet_with_resolution.py` | Full-stack integration (FOOTY_EV_INTEGRATION_DB=1) |

---

## 3. Architectural invariants (Phase 3 step 2–3 additions)

24. **Runtime resolution is deterministic SQL only.** `resolve_event`
    does a `betfair_team_aliases` join followed by a `v_fixtures_epl`
    date-level match. Fuzzy matching runs only in
    `scripts/bootstrap_betfair_aliases.py` with manual review. Never
    call rapidfuzz at runtime.
25. **`betfair_team_aliases` must be populated before paper-trade
    produces bets.** An empty table means 100% unresolved → breaker
    trips. Run `python scripts/bootstrap_betfair_aliases.py` once after
    setting up Betfair credentials.
26. **Kickoff alignment is DATE-level.** `v_fixtures_epl.kickoff_utc` is
    midnight UTC; Betfair `openDate` is a datetime. The SQL join uses
    `CAST(... AS DATE)` equality, not timestamp arithmetic. This prevents
    off-by-one errors around midnight and doesn't require a ±N hour
    window.
27. **`resolved_fixture_ids` is the analyst's preferred input.** When the
    scraper populates it (resolution enabled), the analyst uses those
    warehouse IDs; when it's empty (legacy / no con), it falls back to
    `fixtures_to_process` (Betfair event IDs). This preserves backward
    compat for tests that don't wire a DB connection.
28. **Model loading uses a time-window join.** `xgb_fits` has no FK to
    `backtest_runs`. The loader finds fits via
    `fitted_at BETWEEN backtest_runs.started_at AND completed_at`.
    `_BOOSTER_CACHE` is a module-level dict keyed by `run_id`;
    `clear_booster_cache()` is exported for test isolation.
29. **`audit_noise` column is 0.0 at inference.** The training-time
    canary feature is always zeroed when calling `booster.predict()` in
    `load_production_scorer`. The feature list must still contain the
    column name.

---

## 4. What's next, ordered

### Immediate (operator prerequisites)

1. **Operator: run `scripts/bootstrap_betfair_aliases.py`** once real
   Betfair credentials are in `.env`. This populates
   `betfair_team_aliases` so the scraper can resolve events.
   ```powershell
   python scripts/bootstrap_betfair_aliases.py --db data/warehouse/footy_ev.duckdb
   ```
   Review each candidate (y/n/m). Auto-accepts score ≥ 85.
2. **Operator: run the integration test** (optional, requires credentials
   + data):
   ```powershell
   $env:FOOTY_EV_INTEGRATION_DB = "1"
   python -m pytest tests/integration/test_paper_trade_emits_bet_with_resolution.py -v
   ```
3. **Operator: smoke-run paper-trade:**
   ```powershell
   python run.py paper-trade --once
   ```
   Check the Streamlit "Paper Trading" page → Entity Resolution panel
   should show resolved events. If all show unresolved, the alias table
   needs bootstrap.

### Short-term: Phase 3 step 4

- **`live_odds_snapshots` writes.** Migration 009 created the table,
  dashboard query reads it, but the scraper node does not write to it
  yet. Wire up snapshot persistence so the freshness chart has real data.
- **Cyclical re-run on news deltas** (BLUE_MAP §2.4): real Ollama
  integration in `nodes/news.py`, plus a conditional edge analyst →
  pricing | analyst.
- **Settlement backfill job:** when fixtures complete, back-fill
  `settled_at`, `pnl_gbp`, `closing_odds`, `clv_pct` on paper_bets rows.
- **`run_forever` test:** add a test with a fake sleep + kill-switch;
  currently only `run_once` is tested end-to-end.

### Medium-term

- **Phase 4 prerequisites:** real-money execution path. Gated on
  positive CLV over 500+ paper bets + 60-day paper run + chaos-tested
  bankroll module (PROJECT_INSTRUCTIONS §3).
- **Multi-market extension:** 1X2 and BTTS. Scraper today only fetches
  OVER_UNDER_25 markets; extend `market_types` list and add per-market
  score_fn dispatch.
- **Ambiguous fixture resolution.** When two fixtures share the same
  teams and date (data artifact), `resolve_event` returns "ambiguous"
  and drops the event. Consider a tiebreak heuristic (league priority).

---

## 5. Outstanding TODOs / known debt

### Operator-side
- Rotate the GitHub PAT exposed during the 2026-05-09 push setup (see
  step 1 handoff). `make.ps1 push` now reads it from `.env` cleanly.
- `VIRTUAL_ENV` mismatch warning persists; cosmetic.

### Code-side
- **`live_odds_snapshots` unwritten.** See §4 Short-term.
- **`run_forever` not tested.** Only `run_once` has end-to-end coverage.
- **`risk._hit_per_bet_cap` is a heuristic.** When the operator passes a
  non-default `per_bet_cap_pct`, the audit flag will be wrong.
- **Betfair `resolved_by` column defaults to `'manual'` in migration.**
  The bootstrap script should write `'fuzzy_accepted'` or
  `'fuzzy_reviewed'` depending on the path taken. Currently all rows
  written via the script will still have the default `'manual'`; this is
  cosmetic but worth fixing when the script is next touched.

### Test gaps
- No `run_forever` test.
- Live Betfair test stays skipped in CI. Add a `make.ps1 test-betfair`
  target once credentials are in place.
- `test_paper_trade_emits_bet_with_resolution.py` is opt-in (env gate).
  Consider promoting to a nightly CI target once the warehouse is seeded.

---

## 6. Recent decisions log

Phase 0–2 and Phase 3 step 1 episodes are in prior handoffs.

**Ep 21 — Phase 3 step 2: production model in analyst node (2026-05-10).**
`model_loader.py` uses a time-window join (no FK from `xgb_fits` to
`backtest_runs`) to find the latest booster. `audit_noise` zeroed at
inference. `_BOOSTER_CACHE` dict avoids repeated DuckDB queries.
`NoProductionModelError` surfaces cleanly when no completed run exists.
Test: `test_model_loader.py` (11 tests) + `test_paper_trader_once.py`
updated. Namespace-mismatch workaround (score_fn returning `[]` silently)
removed in step 3.

**Ep 22 — Phase 3 step 3: Betfair→warehouse entity resolution
(2026-05-10).** Migration 010 adds four tables; runtime path uses
deterministic SQL join only (rapidfuzz only in bootstrap script). Scraper
drops unresolved events; >50% failure trips circuit breaker with reason
`unresolved_event`. BettingState gains `resolved_fixture_ids` so analyst
can use warehouse IDs without overwriting `fixtures_to_process`. Kickoff
alignment via DATE-level join. `test_paper_trader_once.py` updated to
seed betfair_team_aliases so the mock event resolves end-to-end.

---

**Episode 23 — Phase 3 step 3 closeout (2026-05-10).** Eight commits:
migration 010 → resolution.py → bootstrap script → orchestration wiring
→ model_loader workaround removal → dashboard panel → tests → this
handoff. Test count: 273 unit, 1 xfailed, integration test gated.

---

## 7. How to resume

1. Read `CLAUDE.md`, this `HANDOFF.md`. Skip BLUE_MAP/PROJECT_INSTRUCTIONS
   unless a new task touches them.
2. Confirm test suite: `.\make.ps1 test` (expect 273 passed, 1 xfailed).
3. Check live state: `python run.py status` (latest backtest run) and
   `python run.py paper-status` (latest paper-trading invocation).
4. Bootstrap Betfair aliases if not done: `python scripts/bootstrap_betfair_aliases.py`.
5. Decide next step from §4 — most likely wire `live_odds_snapshots`
   writes and/or run the paper trader against real Betfair data.
