# Handoff — end of Phase 3 step 1 (LangGraph + Betfair Delayed + paper trader)

> Created **2026-05-09** at the close of Phase 3 step 1. Read this in full
> before doing anything else, then `CLAUDE.md`, then `BLUE_MAP.md` only
> for the section a new task touches. Phase 0–2 history was covered by
> the previous handoff (committed 2026-05-06); compressed to one-liners
> in §6.

---

## 1. Status banner

We are at the **end of Phase 3 step 1**. The paper-trading vertical
slice ships intact:

- Betfair Exchange Delayed-API client (free-tier, 60s lag) with auth +
  three calls + per-response staleness timestamp.
- LangGraph StateGraph with six nodes (scraper / news / analyst /
  pricing / risk / execution), checkpointed to a SQLite file separate
  from the warehouse.
- Paper-trader runtime exposing `python run.py paper-trade [--once]`
  and `python run.py paper-status`.
- DuckDB migration 009 with paper_bets / live_odds_snapshots /
  langgraph_checkpoint_summaries / circuit_breaker_log.
- Streamlit dashboard "Paper Trading" page with breaker status, fixture
  queue, freshness gauge, recent bets table, edge histogram.

**Test suite: 239 unit passed, 1 xfailed (pre-existing migration-002
frozen-header xfail).** Integration: 5 passed, 9 skipped (all
opt-in: Betfair live + warehouse-population + network gates).

The runtime has **not** been exercised against the real Betfair API yet
— that's pending the operator filling in BETFAIR_APP_KEY /
BETFAIR_USERNAME / BETFAIR_PASSWORD. See `docs/SETUP_GUIDE.md` for the
walkthrough.

---

## 2. Key file locations (Phase 3)

| Path | Purpose |
|---|---|
| `src/footy_ev/venues/betfair.py` | Delayed-API client; login + listEvents/listMarketCatalogue/listMarketBook; tenacity retries; BetfairResponse(payload, received_at, source_timestamp, staleness_seconds) |
| `src/footy_ev/venues/exceptions.py` | BetfairAuthError, StaleResponseError |
| `src/footy_ev/orchestration/state.py` | BettingState TypedDict + pydantic OddsSnapshot/ModelProbability/BetDecision |
| `src/footy_ev/orchestration/graph.py` | `build_graph(...)` + `compile_graph(...)` (SqliteSaver-backed checkpoints) |
| `src/footy_ev/orchestration/checkpoints.py` | Summary writer for langgraph_checkpoint_summaries + circuit_breaker_log |
| `src/footy_ev/orchestration/nodes/*.py` | Six nodes; analyst takes a `score_fn` injected by the runtime |
| `src/footy_ev/runtime/paper_trader.py` | `run_once(cfg, ...)` + `run_forever(cfg)` + `_resolve_fixtures_and_markets` |
| `src/footy_ev/db/migrations/009_paper_trading.sql` | Four append-only tables for the paper runtime |
| `dashboard/app.py` | "Paper Trading" sidebar page added |
| `docs/SETUP_GUIDE.md` | Operator walkthrough: Betfair account + Delayed key + .env |
| `data/langgraph_checkpoints.sqlite` | (created on first run) SqliteSaver blob store, separate from the warehouse |

---

## 3. Architectural invariants (Phase 3 additions to the existing 16)

17. **No real-money Betfair execution in step 1.** The execution node
    has zero placeBets call wired up. LIVE_TRADING=true is checked but
    the path lands in paper_bets either way, with a logged warning.
    Real execution is a Phase 4 deliverable.
18. **Idempotency on every external call.** `paper_bets.decision_id`
    is `hash(fixture_id|market|selection|decided_at|venue)[:24]`;
    `live_odds_snapshots.snapshot_id` will use the same pattern when
    the snapshot writer is wired in step 2. Re-running the same
    invocation produces the same row, never a duplicate.
19. **Staleness > 300s trips the circuit breaker.** Threshold lives in
    `orchestration/nodes/scraper.py::STALENESS_LIMIT_SEC`. Every trip
    is logged to circuit_breaker_log with `reason` and
    `affected_source`.
20. **Credentials never in code, never in logs.** All three BETFAIR_*
    vars come from `.env` (gitignored). The Betfair client redacts
    its auth-error messages so credentials never appear in retry
    backtraces or pre-commit hook output.
21. **SQLite checkpoints are isolated from the analytical warehouse.**
    Binary checkpoint blobs live in
    `data/langgraph_checkpoints.sqlite`; queryable summaries live in
    `langgraph_checkpoint_summaries` in DuckDB. The dashboard never
    cracks open the SQLite file.
22. **Analyst node is pure.** It accepts a `score_fn` injected by the
    runtime, never re-trains, and never opens its own DuckDB
    connection. Tests pass a closure; runtime does likewise.
23. **Cyclical re-runs deferred.** BLUE_MAP §2.4 (news → analyst
    re-run on lineup deltas) is Phase 3 step 2, not step 1.

---

## 4. What's next, ordered

### Immediate

1. **Operator: register a Betfair account** (free, no deposit) and
   request a Delayed Application Key. See `docs/SETUP_GUIDE.md` §1–§3.
   Populate the three `BETFAIR_*` vars in `.env`.
2. **Operator: run the live integration test:**
   ```powershell
   $env:FOOTY_EV_BETFAIR_LIVE = "1"
   .\make.ps1 test-integration
   ```
   Pass = creds work and the Delayed API is up.
3. **Operator: smoke-run the paper trader once:**
   ```powershell
   python run.py paper-trade --once
   ```
   Expect either zero candidates (likely — the score_fn is not yet
   wired to the real model) or one of two diagnostic states. Open the
   Streamlit "Paper Trading" page to see breaker status + fixture
   queue.

### Short-term: Phase 3 step 2

- **Wire a real `score_fn` for the analyst node.** Currently
  `runtime.paper_trader.run_once` accepts `score_fn=None` and the
  graph emits zero probabilities — bets are only produced when tests
  inject a closure. Step 2 needs a `score_fn` that:
    1. Loads the latest XGBoost run's fits keyed by run_id.
    2. Builds a snapshot feature row via `features.assembler`.
    3. Calls `predict_ou25` and emits the dict shape the analyst
       expects.
- **Wire `live_odds_snapshots` writes** in the scraper node so the
  freshness chart on the dashboard has real data.
- **Cyclical re-run on news deltas** (BLUE_MAP §2.4): real Ollama
  integration in `nodes/news.py`, plus a conditional edge analyst →
  pricing | analyst (re-run if news_deltas non-empty and re-runs <
  N).
- **Settlement backfill job:** when fixtures complete, look up the
  Betfair SP and write `settled_at`, `pnl_gbp`, `closing_odds`, and
  `clv_pct` to the existing paper_bets rows.
- **Fixture-id alignment:** today the runtime's "fixture_id" is the
  Betfair eventId, which doesn't join against the historical fixture
  namespace. Step 2 should establish the mapping (probably via a
  `betfair_event_id_aliases` table) and join through `v_fixtures`.

### Medium-term

- **Phase 4 prerequisites:** real-money execution path. Has to wait
  on `PROJECT_INSTRUCTIONS §3` bankroll discipline conditions
  (positive CLV on 500+ paper bets, 60-day paper run, chaos-tested
  bankroll module).
- **Multi-market extension:** 1X2 and BTTS in addition to OU 2.5.
  Scraper today only encodes OU 2.5; the selection map needs market-
  specific lookups.

---

## 5. Outstanding TODOs / known debt

### Operator-side
- Rotate the GitHub PAT exposed during the 2026-05-09 push setup;
  `make.ps1 push` now reads it from `.env` cleanly. The old token is
  still stored in GitHub's PAT list — revoke it.
- `VIRTUAL_ENV` mismatch warning persists; cosmetic.

### Code-side
- **`live_odds_snapshots` is unwritten.** Migration 009 created the
  table, the dashboard query reads it, but the scraper node does not
  yet write to it. Step 2 fix.
- **Analyst node has no real `score_fn`.** Runtime constructs the
  graph with `score_fn=None`, so bets are never produced in
  production until step 2 plumbs in the model loader.
- **Betfair "fixture_id" is the Betfair eventId**, not the
  v_fixtures.fixture_id used by Phase 1/2. Cross-system join is not
  yet wired.
- **Staleness lookup is per-call, not per-snapshot.** When a market
  has stale source data, the breaker trips, but individual snapshots
  store `staleness_seconds=0` because we attribute staleness at the
  response level not the runner level. Acceptable for step 1.
- **`risk._hit_per_bet_cap` is a heuristic** (compares f_used to the
  default 0.02 cap). When the operator passes a non-default
  per_bet_cap_pct, the flag will be wrong. Low priority — only the
  audit column is affected.

### Test gaps
- No test exercises `run_forever` (the polling loop). Step 2 should
  add one with a fake sleep and a kill-switch.
- The live Betfair test stays skipped in CI by default. Once a
  Betfair account is set up, the operator should add `--betfair-live`
  to a separate make target so it runs on demand without polluting
  the unit suite.

---

## 6. Recent decisions log (compressed)

Phase 0/1/2 episodes are in the prior handoff (committed 2026-05-06).
The Phase 3 step 1 episodes:

**Ep 16 — Plan-then-implement protocol (2026-05-09).** Operator demanded
plan-mode for Phase 3 step 1, approved the plan as-is, then approved a
straight-through 8-commit implementation. Rule for future big-scope
steps: produce a plan with file list, test plan, migration schema, and
runbook before any commits.

**Ep 17 — SqliteSaver lifetime bug (2026-05-09).** First implementation
of `compile_graph` called `SqliteSaver.from_conn_string(...).__enter__()`
without ever pairing it with `__exit__()`, which closes the underlying
sqlite3 connection on context exit. The graph then crashed on first
invoke with "Cannot operate on a closed database." Fixed by opening a
sqlite3.Connection directly and passing it to `SqliteSaver(conn)` —
runtime owns the connection's lifetime and closes it in the `finally`
block.

**Ep 18 — Ruff/mypy version drift hotfix (2026-05-09).** The ruff
0.13.0 bump in pre-commit broke compatibility with newer rule names
(`TC*`); we keep the legacy `TCH*` aliases in pyproject.toml ignore so
both versions parse the config. mypy hook adds polars/numpy/pandas-stubs
to additional_dependencies so it sees the same types as local.

**Ep 19 — execution-node paper invariant (2026-05-09).** Even with
`LIVE_TRADING=true`, step 1's execution node has no Betfair placeBets
call wired. The flag is checked, a warning is logged, and bets land in
paper_bets. Real placement is gated on Phase 4.

---

**Episode 20 — Phase 3 step 1 closeout (2026-05-09).** Eight commits:
deps → migration 009 → Betfair client → orchestration scaffold → paper-
trader runtime → integration tests → dashboard page → this handoff.
Test count: 239 unit, 5 integration, 1 xfailed, several opt-in skips.

---

## 7. How to resume

1. Read `CLAUDE.md`, this `HANDOFF.md`. Skip BLUE_MAP/PROJECT_INSTRUCTIONS
   unless a new task touches them.
2. Confirm test suite: `.\make.ps1 test` (expect 239 passed, 1 xfailed).
3. Check live state: `python run.py status` (latest backtest run) and
   `python run.py paper-status` (latest paper-trading invocation).
4. Decide next step from §4 above — most likely start by wiring the
   real `score_fn` so the analyst node produces actual probabilities.
