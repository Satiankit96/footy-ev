# Frontend Stage 11 — Diagnostics & Audit

> Progress: 10 of 15 stages complete (~67%). Starting Stage 11 of 15.

## Mission

Build the diagnostics dashboard (circuit breaker, logs, migrations, env) and the audit trail system. This is the stage where the **operator-actions audit middleware** lands — every state-mutating endpoint across the entire app gets retroactive audit logging. Also: the `operator_actions` table migration that §20.7 deferred to this stage.

## Read first

1. `CLAUDE.md`
2. `frontend/PLAN.md`:
   - §3 rules 4+5 (destructive confirmations, audit logging requirement)
   - §7.12 (Diagnostics API — 5 endpoints)
   - §7.13 (Audit API — 3 endpoints)
   - §8.11 (`/diagnostics` pages UX)
   - §8.12 (`/audit` page UX)
   - §12 Stage 11 acceptance criteria
   - §20.7 (operator_actions table — migration lives in main project)
3. Existing code:
   - `src/footy_ev/db/migrations/` — find the next migration number (was 014 for Stage 5's alias status; check what's current)
   - `src/footy_ev/db/schema.sql` — for reference
   - All existing mutating endpoints across Stages 3–10 (pipeline/cycle, bootstrap/run, aliases/create, aliases/retire, predictions/run, clv/backfill, circuit-breaker/reset) — the middleware must cover all of them
   - `frontend/api/src/footy_ev_api/main.py` — where middleware gets registered

## Deliverables

### A. Migration — `operator_actions` table

Per §20.7, add `migration_NNN_operator_actions.sql` in `src/footy_ev/db/migrations/` (find next sequential number). Schema:

```sql
CREATE TABLE IF NOT EXISTS operator_actions (
    action_id     VARCHAR PRIMARY KEY,
    action_type   VARCHAR NOT NULL,      -- 'pipeline_cycle', 'bootstrap_run', 'alias_create', 'alias_retire', 'prediction_run', 'clv_backfill', 'circuit_breaker_reset', etc.
    operator      VARCHAR NOT NULL DEFAULT 'operator',  -- single-user
    performed_at  TIMESTAMP NOT NULL,
    input_params  JSON,                  -- request body or query params, sanitized (no secrets)
    result_summary VARCHAR,              -- short outcome description
    request_id    VARCHAR                -- correlates with API request
);
```

Append-only. No UPDATE, no DELETE.

**Checkpoint A:**
- Migration filename + number
- Confirm append-only (no UPDATE/DELETE in migration or anywhere referencing this table)

### B. Audit middleware

FastAPI middleware (or dependency) that intercepts every state-mutating request (POST, PUT, DELETE methods on relevant routes) and writes an `operator_actions` row **after** the handler completes successfully.

Requirements:
- Captures: action_type (derived from route path), input_params (sanitized — strip any field containing "token", "key", "secret", "password"), result_summary (from response or handler metadata), request_id, timestamp
- Only logs successful mutations (2xx responses). Failed requests (4xx/5xx) are not audit-logged.
- Does not block the response — if audit write fails, log a warning but return the response normally
- Covers **all existing mutating endpoints**: pipeline/cycle, pipeline/loop/start, pipeline/loop/stop, bootstrap/run, aliases/create, aliases/retire, predictions/run, clv/backfill, circuit-breaker/reset, and any POST/PUT on settings

List every endpoint the middleware covers in the final report.

**Checkpoint B:**
- Middleware registration point (cite file + line)
- Full list of endpoints covered
- Confirm sanitization of secrets from input_params
- Confirm non-blocking on audit write failure

### C. Backend — Diagnostics router

Per §7.12:
- `GET  /api/v1/diagnostics/circuit-breaker` — state (ok/tripped), last trip reason, last trip timestamp
- `POST /api/v1/diagnostics/circuit-breaker/reset` — manual reset with confirmation. **Must be audit-logged** (test this specifically).
- `GET  /api/v1/diagnostics/logs?level=&since=&limit=` — tail from rotating log file (find where the app logs — if no file-based logging exists, set up a basic `RotatingFileHandler` in the API)
- `GET  /api/v1/diagnostics/migrations` — list of migration files with applied/pending status and timestamps
- `GET  /api/v1/diagnostics/env` — sanitized env check: list of expected env vars with set/unset indicator. **Never return values.** Expected vars: `UI_OPERATOR_TOKEN`, `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`, `KALSHI_BASE_URL`, `DATABASE_PATH`, `LIVE_TRADING`, `LLM_EXTRACTOR`, etc. (discover from existing `.env.example` files)

**Checkpoint C:**
- Endpoints implemented
- Confirm circuit-breaker reset is audit-logged (cite the test)
- Confirm env endpoint never returns values (cite the response schema)
- Backend test count delta

### D. Backend — Audit router

Per §7.13:
- `GET /api/v1/audit/operator-actions?action_type=&since=&limit=&offset=` — paginated operator actions from the new table
- `GET /api/v1/audit/model-versions` — all registered model versions from `model_predictions` (DISTINCT model_version with first/last seen timestamps, count of predictions)
- `GET /api/v1/audit/decisions?since=&limit=&offset=` — paper bet decisions audit trail (similar to `/bets` but focused on the decision chain: prediction → pricing → risk → execution)

**Checkpoint D:**
- Endpoints implemented
- Backend test count delta

### E. Frontend — `/diagnostics` + sub-pages

Per §8.11:
- `/diagnostics` main page:
  - Circuit breaker panel: green/red LED (reuse existing `CircuitBreakerLED` from Stage 1 topbar), state label, last trip reason + timestamp, **Reset button** with AlertDialog typed confirmation (`TYPE RESET-BREAKER`)
  - Migrations panel: table of migration files, applied (green) / pending (yellow) status
  - Env panel: table of expected vars, set (green check) / unset (red x). No values shown.

- `/diagnostics/logs`:
  - Log tail table: timestamp, level (color-coded), message
  - Filters: level (DEBUG/INFO/WARNING/ERROR), time range
  - **"Live" toggle:** when on, auto-refreshes every 5s via polling (not WS — simple setInterval + refetch)
  - Search field filters within currently loaded results (client-side)

- `/diagnostics/circuit-breaker` (if the main page circuit breaker section is enough, this can redirect there — don't build a separate page if redundant)

**Checkpoint E:**
- Reset confirmation pattern (typed phrase)
- Live toggle polling mechanism
- Frontend test count delta

### F. Frontend — `/audit` page

Per §8.12:
- Tabs or sections:
  1. **Operator Actions:** table from `/audit/operator-actions` — timestamp, action_type badge, input summary (truncated), result summary. Filterable by action_type. Paginated.
  2. **Model Versions:** table from `/audit/model-versions` — version, first seen, last seen, prediction count. Current production version highlighted if identifiable.
  3. **Bet Decisions:** table from `/audit/decisions` — decision chain view per bet.

**Checkpoint F:**
- Tab/section structure
- Frontend test count delta

### G. Carry-over review — Stage 5 retire UPSERT

Per the carry-over flagged in Stages 5/6: the retire flow uses `INSERT...ON CONFLICT DO UPDATE SET status='retired'` because `kalshi_event_aliases.event_ticker` is PRIMARY KEY. This technically violates the append-only invariant.

**Review and recommend** (in the final report, not as code changes):
- Is this pragmatic and acceptable given the single-PK constraint?
- Or should a future migration change the PK to composite `(event_ticker, status_change_seq)` to enable true append?
- What's your recommendation? One paragraph, no code changes this stage.

## Known pre-existing issues (do NOT fix)

- 2 pre-existing pytest failures: `test_start_cycle`, `test_start_cycle_conflict` — ignore.

## Hard constraints

1. **No `git push`, no remote sync.** Local commits + `frontend-stage-11-complete` tag only.
2. **`src/footy_ev/` edits limited to:** the new migration SQL file only. Nothing else.
3. **No new deps in main project `pyproject.toml`.**
4. **No scope creep into Stage 12 (Live trading gate).**
5. **mypy --strict clean** backend. **tsc --noEmit clean** frontend.
6. **Audit table is append-only.** No UPDATE or DELETE against `operator_actions`.
7. **Env endpoint never returns secret values.** Set/unset boolean only.

## Required final report

1. **Checkpoints A–G** verbatim.
2. **Test counts:** backend before/after, frontend before/after. Confirm green: `pnpm typecheck`, `pnpm lint`, `pnpm test`, `uv run mypy --strict`, `uv run ruff check`, `uv run pytest` (note pre-existing failures separately).
3. **Files touched in `src/footy_ev/`** — should be migration file only.
4. **Full list of mutating endpoints covered by audit middleware.**
5. **§12 Stage 11 acceptance check:**
   - [ ] Every mutating action across the app produces an audit row
   - [ ] Manual circuit breaker reset is logged
   - [ ] Log tail updates live when "Live" toggle is on
6. **Deviations from spec** — bullet list with justification, or "none."
7. **Any constraint violations or scope creep — explicit list, even if zero.**
8. **Brief summary of what you did** — 5–8 sentences, plain English. What shipped, what was tricky, what was deferred, what to expect in Stage 12.
