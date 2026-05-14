# footy-ev Frontend Module — Build Plan

> Operator-facing single-page application that exposes every part of the footy-ev betting system through a real UI. Lives in `frontend/` alongside the main `src/footy_ev/` code; isolated like the Twitter module so it can be developed and deleted independently.

> This plan is the source of truth. Implement in the staged order in §12. Treat each stage as a separate work session with its own acceptance criteria. Don't skip ahead — earlier stages set foundations later stages depend on.

---

## 0. Purpose & Goals

Build a production-quality web UI that lets the operator:

1. **See** every piece of state the backtest/paper-trading system has — fixtures, aliases, predictions, paper bets, CLV history, Kalshi market data, freshness gauges, circuit breaker state, model registry, audit trail.
2. **Do** every operator-side action that's currently a `run.py` subcommand or a manual SQL query — trigger pipeline cycles, run bootstrap, schedule loops, run CLV backfill, browse the warehouse, inspect a paper bet's full audit, calibrate Kelly hypothetically.
3. **Trust** the system through visual confirmation — freshness gauges, circuit breaker indicator, demo/prod venue indicator, LIVE_TRADING refusal banner, model-version stamp on every prediction.

This replaces `run.py` as the primary operator interface. `run.py` stays as a CLI fallback for headless ops and cron scheduling, but the UI is the daily driver.

The UI is a **single-user, single-operator tool**. Not multi-tenant. No customer-facing surface. Auth exists to prevent casual access if the laptop is unlocked, not to defend against attackers.

---

## 1. Why a Separate Folder + Separate Tech Stack

Same pattern as the `twitter/` module: total isolation. Three reasons:

1. **Different ecosystem hygiene.** Node tooling (npm/pnpm, ESLint, Prettier, TypeScript compiler) doesn't belong mixed into a Python project's root. Keep them in their own corner with their own `package.json` and `pyproject.toml`.
2. **Independent failure isolation.** A bad Next.js dependency upgrade should not be able to break `make test` on the main project. The main Python code runs without the UI being functional or even installed.
3. **Optional integration.** The FastAPI layer reads from `src/footy_ev/`. The Next.js layer reads from FastAPI. If the operator wants to nuke the UI someday, deleting `frontend/` leaves the main pipeline untouched.

---

## 2. Architectural Decision: FastAPI + Next.js + TypeScript

**Backend: FastAPI** (Python 3.12, uvicorn ASGI server).

Why: the entire business logic — model training, scraping, pricing, Kelly math, settlement, CLV — already lives in Python under `src/footy_ev/`. Rewriting any of it in another language is wasted work. FastAPI wraps the existing functions, adds HTTP/WebSocket transport, and exposes an OpenAPI schema. The backend is a thin transport layer; it imports from `src/footy_ev/` and adds nothing operational.

**Frontend: Next.js 15 with App Router + TypeScript 5.5 + React 19**.

Why this over alternatives:

- *vs. Streamlit (current `dashboard/`)*: Streamlit is fine for monitoring but caps out hard on interactivity. Forms, multi-step workflows, real-time updates, custom layouts, and proper state management all fight against Streamlit's execution model. The operator wants this to be a daily driver — Streamlit hits a wall.
- *vs. plain Vite + React*: Next.js gives batteries-included routing, server components (useful for data-heavy views), file-based code organization, and a single canonical "how do I do X" answer to most questions. Less decision fatigue, faster bootstrap, better Codex/Claude pattern matching since Next.js is the most common React framework.
- *vs. SvelteKit*: Smaller ecosystem; Codex and Claude have less training signal on it. React stays the safer pick for AI-assisted dev.
- *vs. Tauri/Electron*: Local-first desktop app would be defensible but adds packaging complexity for marginal benefit. Web served on `localhost` from the same machine gives 95% of the desktop benefit with 30% of the complexity. Revisit if the operator ever wants a true offline desktop binary.

**Why TypeScript over plain JS**: prevents an entire class of "field renamed, frontend broke silently" bugs. The API client types are auto-generated from FastAPI's OpenAPI spec (see §7.13). FE and BE stay in sync by construction.

**Why both halves live in `frontend/`**: keeping the FastAPI app inside `frontend/api/` rather than at the project root makes the separation explicit. The main project does not depend on FastAPI being installed.

---

## 3. Critical Safety Boundaries (Read This First)

These rules are immutable. Every stage respects them. Codex/Opus must surface and pause before violating any.

1. **The UI never bypasses `LIVE_TRADING` gating.** The backend reads `LIVE_TRADING` from the same `.env` the main pipeline reads. If it's `true`, the backend refuses to start with a hard error. Setting it via the UI is not an exposed feature. Live trading is enabled the same way it has always been — by editing `.env` after PROJECT_INSTRUCTIONS §3 conditions are independently validated.

2. **The UI never reads or displays the Kalshi private key, API key ID, or any other secret.** The Settings page shows a green/red "credentials configured" indicator only. If the operator wants to verify or rotate credentials, they edit `.env` directly. The API surface never returns secret values.

3. **The UI never writes to the main warehouse from the browser directly.** All writes route through FastAPI handlers that perform the same pydantic validation and entity resolution the existing Python pipeline does. There is no "raw SQL execution" endpoint.

4. **Destructive operations require explicit confirmation.** Anything that mutates state (run bootstrap, trigger settlement, manually invalidate an alias) shows a modal dialog with the exact effect and a typed confirmation phrase (e.g., type "BOOTSTRAP" to proceed). No one-click "delete all" buttons exist.

5. **All mutations are logged to an `operator_actions` audit table.** Who (operator, since single-user), when, what action, what input parameters. Append-only. The audit trail is visible on the Audit page.

6. **The UI auth model is one shared operator-token, configurable in `.env`.** No password reset flow, no email, no multi-user. If someone has the token, they're the operator. Defense in depth means the token is randomly generated and high-entropy; not a "real" auth system.

7. **The backend is bound to `127.0.0.1` by default, never `0.0.0.0`.** Local-first means local-only. To expose remotely (Codespaces, etc.) requires an explicit env flag and the operator-token check is enforced. The frontend dev server is similarly local-only by default.

8. **No analytics, no telemetry, no third-party tracking scripts in the UI.** This is an operator tool, not a product. Outbound network from the frontend is limited to the local FastAPI backend, with the single exception of CDN-loaded fonts (which can be self-hosted if the operator wants zero outbound — make this configurable).

---

## 4. Main Project Context for Codex/Opus

### 4.1 What footy-ev is

Local-first +EV sports-betting pipeline for European football pre-match markets, currently targeting EPL Over/Under 2.5 goals contracts on Kalshi. Paper-trading mode only. ~88% complete as of the start of this frontend build. Phase 3 step 5c (Kalshi venue + run.py orchestrator + bootstrap) just landed.

For full context, read in this order: `CLAUDE.md`, `README.md`, `BLUE_MAP.md` (skip §10 unless referenced), `PROJECT_INSTRUCTIONS.md`, `HANDOFF.md`.

### 4.2 What already exists and the UI will surface

- **Pipeline orchestration** via LangGraph nodes in `src/footy_ev/orchestration/`: scraper → analyst → pricing → risk → execution → settlement → CLV backfill
- **Kalshi venue** in `src/footy_ev/venues/kalshi.py`: RSA-PSS auth, list/get events/markets, OU 2.5 floor_strike filter, Pydantic-modeled responses
- **Models** in `src/footy_ev/models/`: xG-Skellam OU 2.5 (MARGINAL_SIGNAL), XGBoost stacked (best signal), Dixon-Coles 1X2 (parked)
- **Warehouse** at `data/footy_ev.duckdb` with schema in `src/footy_ev/db/schema.sql` and migrations under `src/footy_ev/db/migrations/`
- **`run.py`** unified orchestrator with cycle/loop/dashboard/status/bootstrap subcommands

### 4.3 Project rules that apply to the UI

- **No new top-level Python dependencies in `pyproject.toml` for main project.** FastAPI lives in `frontend/api/pyproject.toml`, a separate uv-managed project. Main project's deps stay untouched.
- **`mypy --strict` clean** on every Python file in `frontend/api/src/`.
- **`tsc --noEmit` clean** on every TypeScript file in `frontend/web/`.
- **No floats for money in API responses.** Decimal serialized as string ("1.9234") to preserve precision across the JSON boundary.
- **Append-only ledgers in the warehouse.** No UI action `UPDATE`s or `DELETE`s rows from `paper_bets`, `model_predictions`, `odds_snapshots`, `kalshi_event_aliases`, or `events_ledger`. Aliases can be invalidated by appending a `status='retired'` row; the historical record is preserved.

---

## 5. Folder Layout

```
footy-ev/
├── frontend/
│   ├── PLAN.md                      ← this file
│   ├── README.md                    ← Codex generates after stage 0
│   ├── docker-compose.yml           ← optional, for prod-style local run
│   ├── .env.example                 ← UI-specific env vars
│   ├── api/                         ← FastAPI backend
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   ├── src/footy_ev_api/
│   │   │   ├── __init__.py
│   │   │   ├── main.py              ← FastAPI app factory + uvicorn entry
│   │   │   ├── settings.py          ← Pydantic Settings from .env
│   │   │   ├── deps.py              ← Dependency-injection container
│   │   │   ├── auth.py              ← Operator-token middleware
│   │   │   ├── errors.py            ← Typed exceptions + handlers
│   │   │   ├── routers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── pipeline.py
│   │   │   │   ├── kalshi.py
│   │   │   │   ├── aliases.py
│   │   │   │   ├── bootstrap.py
│   │   │   │   ├── fixtures.py
│   │   │   │   ├── predictions.py
│   │   │   │   ├── bets.py
│   │   │   │   ├── clv.py
│   │   │   │   ├── risk.py
│   │   │   │   ├── warehouse.py
│   │   │   │   ├── diagnostics.py
│   │   │   │   ├── audit.py
│   │   │   │   ├── live_trading.py
│   │   │   │   └── settings.py
│   │   │   ├── ws/
│   │   │   │   ├── pipeline.py
│   │   │   │   └── freshness.py
│   │   │   ├── jobs/
│   │   │   │   ├── manager.py       ← In-process job tracking
│   │   │   │   ├── pipeline_cycle.py
│   │   │   │   ├── bootstrap.py
│   │   │   │   └── clv_backfill.py
│   │   │   ├── adapters/            ← Thin wrappers around src/footy_ev/
│   │   │   │   ├── pipeline.py
│   │   │   │   ├── kalshi.py
│   │   │   │   ├── warehouse.py
│   │   │   │   └── runtime.py
│   │   │   └── schemas/             ← Pydantic response/request shapes
│   │   │       ├── pipeline.py
│   │   │       ├── kalshi.py
│   │   │       └── ...
│   │   └── tests/
│   │       ├── unit/
│   │       ├── integration/
│   │       └── fixtures/
│   └── web/                         ← Next.js frontend
│       ├── package.json
│       ├── pnpm-lock.yaml
│       ├── next.config.ts
│       ├── tailwind.config.ts
│       ├── tsconfig.json
│       ├── .eslintrc.json
│       ├── prettier.config.mjs
│       ├── playwright.config.ts
│       ├── vitest.config.ts
│       ├── app/                     ← Next.js App Router pages
│       │   ├── layout.tsx
│       │   ├── page.tsx
│       │   ├── globals.css
│       │   ├── pipeline/page.tsx
│       │   ├── kalshi/
│       │   │   ├── page.tsx
│       │   │   ├── events/page.tsx
│       │   │   ├── events/[ticker]/page.tsx
│       │   │   └── markets/[ticker]/page.tsx
│       │   ├── aliases/
│       │   │   ├── page.tsx
│       │   │   └── create/page.tsx
│       │   ├── fixtures/
│       │   │   ├── page.tsx
│       │   │   └── [id]/page.tsx
│       │   ├── predictions/
│       │   │   ├── page.tsx
│       │   │   └── [id]/page.tsx
│       │   ├── bets/
│       │   │   ├── page.tsx
│       │   │   └── [id]/page.tsx
│       │   ├── clv/page.tsx
│       │   ├── risk/page.tsx
│       │   ├── warehouse/
│       │   │   ├── page.tsx
│       │   │   ├── teams/page.tsx
│       │   │   ├── teams/[id]/page.tsx
│       │   │   ├── players/page.tsx
│       │   │   └── snapshots/page.tsx
│       │   ├── diagnostics/
│       │   │   ├── page.tsx
│       │   │   ├── logs/page.tsx
│       │   │   └── circuit-breaker/page.tsx
│       │   ├── audit/page.tsx
│       │   ├── live-trading/page.tsx
│       │   ├── settings/page.tsx
│       │   └── login/page.tsx
│       ├── components/
│       │   ├── ui/                  ← shadcn/ui components, copy-pasted in
│       │   ├── charts/              ← Tremor or Recharts wrappers
│       │   ├── tables/              ← TanStack Table wrappers
│       │   ├── layout/
│       │   │   ├── app-shell.tsx
│       │   │   ├── sidebar.tsx
│       │   │   ├── topbar.tsx
│       │   │   ├── venue-pill.tsx
│       │   │   ├── live-trading-banner.tsx
│       │   │   └── circuit-breaker-led.tsx
│       │   ├── forms/
│       │   └── feature/             ← Domain-specific composites
│       │       ├── pipeline/
│       │       ├── kalshi/
│       │       ├── aliases/
│       │       ├── bets/
│       │       ├── clv/
│       │       └── risk/
│       ├── lib/
│       │   ├── api/
│       │   │   ├── client.ts        ← Typed fetch wrapper
│       │   │   ├── types.gen.ts     ← Auto-generated from OpenAPI
│       │   │   ├── ws.ts
│       │   │   └── hooks/           ← TanStack Query hooks per endpoint
│       │   ├── stores/              ← Zustand client-state stores
│       │   ├── utils/
│       │   │   ├── decimal.ts       ← Decimal-as-string helpers
│       │   │   ├── format.ts        ← Currency, percentages, datetimes
│       │   │   └── env.ts
│       │   └── theme.ts
│       ├── public/                  ← Static assets
│       │   └── fonts/               ← Self-hosted fonts
│       └── tests/
│           ├── unit/                ← Vitest
│           └── e2e/                 ← Playwright
```

---

## 6. Tech Stack with Version Pins

### 6.1 Backend (`frontend/api/`)

| Package | Version | Why |
|---|---|---|
| `python` | 3.12+ | Matches main project |
| `fastapi` | `^0.115` | HTTP + WebSocket + OpenAPI |
| `uvicorn[standard]` | `^0.32` | ASGI server |
| `pydantic` | `^2.9` | Matches main project |
| `pydantic-settings` | `^2.6` | Env-driven config |
| `httpx` | `^0.27` | Already in main project |
| `python-jose[cryptography]` | `^3.3` | For token auth |
| `duckdb` | matches main project | DB access |
| `python-multipart` | `^0.0.12` | Form parsing if needed |
| `websockets` | `^13.1` | WebSocket transport |
| `pytest` | `^8.3` | Tests |
| `pytest-asyncio` | `^0.24` | Async test support |
| `httpx[testing]` | for TestClient | API tests |
| `mypy` | `^1.13` | Strict typing |
| `ruff` | latest | Lint + format |

Main project dependency: the backend imports `footy_ev` from `src/footy_ev/`. Add this to `frontend/api/pyproject.toml` as an editable install pointing at `../../` so the API picks up live changes during development.

### 6.2 Frontend (`frontend/web/`)

| Package | Version | Why |
|---|---|---|
| `next` | `15.x` | App Router, React 19 support |
| `react`, `react-dom` | `^19` | Latest stable |
| `typescript` | `^5.5` | Strict mode on |
| `tailwindcss` | `^3.4` | Utility CSS |
| `@tanstack/react-query` | `^5.59` | Server state, caching, optimistic updates |
| `@tanstack/react-table` | `^8.20` | Headless table primitives |
| `zustand` | `^5.0` | Client-only state (UI prefs, transient state) |
| `react-hook-form` | `^7.53` | Forms |
| `zod` | `^3.23` | Form validation, runtime type checks |
| `@hookform/resolvers` | `^3.9` | Bridge react-hook-form ↔ zod |
| `recharts` | `^2.13` | Chart primitives |
| `@tremor/react` | `^3.18` | Higher-level dashboard charts on top of Recharts |
| `lucide-react` | latest | Icons |
| `clsx`, `tailwind-merge` | latest | Conditional class helpers |
| `next-themes` | `^0.4` | Dark/light mode |
| `sonner` | `^1.5` | Toast notifications |
| `@radix-ui/*` | `latest` | Underlying primitives for shadcn/ui |
| `openapi-typescript` | `^7.4` | Generate `types.gen.ts` from FastAPI's `/openapi.json` |
| `decimal.js` | `^10.4` | Decimal handling on the FE |
| `date-fns` | `^4.1` | Date formatting |

Dev:
| `eslint`, `eslint-config-next` | latest | Lint |
| `prettier`, `prettier-plugin-tailwindcss` | latest | Format |
| `vitest`, `@testing-library/react`, `@testing-library/jest-dom` | latest | Unit + component tests |
| `playwright`, `@playwright/test` | latest | E2E |
| `msw` | `^2.4` | Mock Service Worker for FE tests against the API |

Package manager: `pnpm`. Faster, stricter than npm/yarn. Lockfile committed.

UI library: **shadcn/ui** components copy-pasted into `components/ui/` via `npx shadcn@latest add <component>`. Not a dependency; the components live in the repo and the operator owns them.

---

## 7. Backend — Complete API Surface

All endpoints under `/api/v1/`. JSON in, JSON out. Decimal serialized as string. Datetime serialized as ISO 8601 UTC. Auth via `Authorization: Bearer <operator-token>` header except `/api/v1/health` and `/api/v1/auth/login`.

OpenAPI schema exposed at `/openapi.json` and rendered at `/docs` (Swagger UI) and `/redoc`. Both Swagger and ReDoc require the operator token (custom Swagger UI loader passes the token from the dashboard's localStorage on the same origin).

### 7.1 Health & auth

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Liveness probe. Returns `{status: "ok", version, uptime_s}`. No auth. |
| POST | `/api/v1/auth/login` | Body: `{token: string}`. Validates against env. Returns 200 + sets HttpOnly session cookie, or 401. |
| POST | `/api/v1/auth/logout` | Clears session cookie. Always 200. |
| GET | `/api/v1/auth/me` | Returns `{operator: "operator", session_started_at}` for the current session. |

### 7.2 Pipeline

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/pipeline/status` | Current pipeline state: last cycle timestamp, breaker state, freshness per source. |
| POST | `/api/v1/pipeline/cycle` | Start one cycle. Returns `{job_id, status: "queued"}`. Subscribe via WS for progress. |
| POST | `/api/v1/pipeline/loop/start` | Body: `{interval_min: int}`. Starts background loop. Returns `{loop_id, interval_min}`. |
| POST | `/api/v1/pipeline/loop/stop` | Stops the active loop. Idempotent. |
| GET | `/api/v1/pipeline/loop` | Returns current loop state: `{active: bool, interval_min, started_at, last_cycle_at}`. |
| GET | `/api/v1/pipeline/freshness` | Per-source freshness in seconds + warning thresholds. |
| GET | `/api/v1/pipeline/jobs?status=&limit=` | Recent pipeline-cycle jobs. |
| GET | `/api/v1/pipeline/jobs/{job_id}` | Single job detail with timing per node. |

### 7.3 Kalshi

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/kalshi/health` | Hits `_signing_headers`-protected GET on `/series`. Returns `{ok: bool, base_url, latency_ms, clock_skew_s}`. |
| GET | `/api/v1/kalshi/series` | List of available series on configured venue. |
| GET | `/api/v1/kalshi/events?series=KXEPLTOTAL&status=open&limit=` | Events under a series. |
| GET | `/api/v1/kalshi/events/{event_ticker}` | Event detail + market list (OU 2.5 only by default; pass `?all_thresholds=1` to see others). |
| GET | `/api/v1/kalshi/markets/{ticker}` | Single market detail with current YES/NO bid/ask and sizes. |
| GET | `/api/v1/kalshi/credentials/status` | Returns `{configured: bool, key_id_present: bool, private_key_path_present: bool, base_url, base_url_is_demo: bool}`. Never returns the values. |

### 7.4 Aliases

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/aliases?status=active&limit=` | List Kalshi event aliases. |
| GET | `/api/v1/aliases/{kalshi_event_ticker}` | Single alias detail including the resolved fixture and contract resolutions. |
| POST | `/api/v1/aliases` | Body: full alias record. Manual creation when bootstrap fails. Validates fixture exists. |
| POST | `/api/v1/aliases/{ticker}/retire` | Appends `status='retired'` row. Idempotent. Original row preserved. |
| GET | `/api/v1/aliases/conflicts` | Aliases pointing at the same fixture, ambiguous matches, etc. |

### 7.5 Bootstrap

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/bootstrap/run` | Body: `{mode: "live" | "fixture", create_fixtures: bool, fixture_path?: string}`. Returns `{job_id}`. WS for progress. |
| GET | `/api/v1/bootstrap/jobs?limit=` | History of bootstrap jobs. |
| GET | `/api/v1/bootstrap/jobs/{job_id}` | Detail: events processed, auto-accepted, needs-review, skipped, errors. |
| GET | `/api/v1/bootstrap/preview?mode=` | Dry-run: returns what would happen without writing. |

### 7.6 Fixtures

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/fixtures?status=&league=&season=&from=&to=&limit=&offset=` | Paginated fixture list. |
| GET | `/api/v1/fixtures/{fixture_id}` | Fixture detail + linked Kalshi aliases + predictions + bets. |
| GET | `/api/v1/fixtures/upcoming?days=14` | Convenience: scheduled fixtures in the next N days with alias status. |

### 7.7 Predictions

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/predictions?fixture_id=&model_version=&limit=` | Predictions ledger. |
| GET | `/api/v1/predictions/{prediction_id}` | Detail: p_raw, p_calibrated, sigma_p, features hash, model version, full feature vector. |
| POST | `/api/v1/predictions/run` | Body: `{fixture_ids?: list[str]}`. If omitted, runs on all scheduled-and-aliased upcoming fixtures. Returns `{job_id}`. |
| GET | `/api/v1/predictions/{prediction_id}/features` | Feature vector that produced the prediction, named per feature view. |

### 7.8 Paper bets

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/bets?status=&fixture_id=&venue=&from=&to=&limit=&offset=` | Paper bets ledger. |
| GET | `/api/v1/bets/{decision_id}` | Detail with full audit: prediction, edge math, Kelly calc, odds quoted vs taken, settlement, CLV. |
| GET | `/api/v1/bets/clv/rolling?window=100` | Rolling CLV time series. |
| GET | `/api/v1/bets/summary?period=7d|30d|all` | Aggregate: total bets, wins, ROI, mean CLV, max drawdown. |

### 7.9 CLV

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/clv/rolling?window=100&since=` | Rolling N-bet CLV. |
| GET | `/api/v1/clv/breakdown?fixture_id=` | Per-fixture CLV decomposition. |
| GET | `/api/v1/clv/sources` | Which CLV benchmark was used per bet (Kalshi close vs Pinnacle historical vs missing). |
| POST | `/api/v1/clv/backfill` | Body: `{from: date, to: date}`. Returns `{job_id}`. |

### 7.10 Risk

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/risk/exposure` | Current exposure: per-day, per-fixture, total open. |
| GET | `/api/v1/risk/bankroll` | Current bankroll, base bankroll, drawdown from peak. |
| POST | `/api/v1/risk/kelly-preview` | Body: `{p_hat, sigma_p, odds, base_fraction, uncertainty_k, per_bet_cap_pct, recent_clv_pct, bankroll}`. Returns the stake. Pure function exposed for "what would I bet if..." exploration. No side effects. |

### 7.11 Warehouse explorer

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/warehouse/tables` | All tables with row counts and last-write timestamps. |
| GET | `/api/v1/warehouse/teams?league=EPL` | Teams listing. |
| GET | `/api/v1/warehouse/teams/{team_id}` | Team + rolling form + upcoming fixtures. |
| GET | `/api/v1/warehouse/players?team_id=` | Players listing (limited surface for now). |
| GET | `/api/v1/warehouse/odds-snapshots?fixture_id=&market=&venue=&limit=` | Paginated snapshots. |
| POST | `/api/v1/warehouse/query` | **Read-only** parameterized query against a fixed allowlist of canned queries. NOT raw SQL execution. Body: `{query_name, params}`. Returns rows. |

The "raw SQL" temptation must be resisted. The allowlist approach lets the operator browse but never lets the UI become an arbitrary SQL execution surface.

### 7.12 Diagnostics

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/diagnostics/circuit-breaker` | State + last-trip reason + last-trip timestamp. |
| POST | `/api/v1/diagnostics/circuit-breaker/reset` | Manual reset with confirmation. Logs to audit. |
| GET | `/api/v1/diagnostics/logs?level=&since=&limit=` | Log tail from rotating log file. |
| GET | `/api/v1/diagnostics/migrations` | List of applied migrations with timestamps. |
| GET | `/api/v1/diagnostics/env` | Sanitized env: shows which keys are set without values. Never returns secrets. |

### 7.13 Audit

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/audit/operator-actions?since=&limit=` | What the operator did and when. |
| GET | `/api/v1/audit/model-versions` | All models registered + which is production. |
| GET | `/api/v1/audit/decisions?since=&limit=` | Paper bet audit trail. |

### 7.14 Live trading (gated)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/live-trading/status` | Returns `{enabled: false, gate_reasons: [list of unmet conditions]}`. Always `enabled: false` until Phase 4 conditions are validated. |
| POST | `/api/v1/live-trading/check-conditions` | Runs the PROJECT_INSTRUCTIONS §3 checks against the warehouse. Returns each condition + pass/fail + observed value. Read-only. |

There is intentionally NO endpoint to enable live trading via the UI. Enabling is done by editing `.env`. The UI's job is to make the gate-reasons visible.

### 7.15 Settings

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/settings` | UI preferences (theme, density, etc.) — operator-scoped, persisted server-side. |
| PUT | `/api/v1/settings` | Body: full settings object. Atomic replace. |

### 7.16 WebSockets

| Path | Payload | Purpose |
|---|---|---|
| `/ws/v1/pipeline` | `{type: "cycle_started"|"node_complete"|"cycle_finished"|"breaker_tripped", payload}` | Live pipeline state. |
| `/ws/v1/freshness` | `{source, last_seen_at, age_seconds}` every 5s | Freshness gauges. |
| `/ws/v1/jobs/{job_id}` | Per-job progress events | For long-running jobs. |

Authentication on WS: query-param token, validated on upgrade. Connection closes on auth failure.

### 7.17 Error envelope

All error responses follow:

```json
{
  "error": {
    "code": "ALIAS_NOT_FOUND",
    "message": "No alias for ticker KXEPLTOTAL-26MAY24WHULEE",
    "details": {"ticker": "KXEPLTOTAL-26MAY24WHULEE"},
    "request_id": "req_abc123"
  }
}
```

Error codes are an enum exported as a TS type to the frontend.

---

## 8. Frontend — Complete Route Map & Page Designs

Every page is responsive (mobile considered, but optimized for desktop 1440×900 and ultrawide). Dark mode is default; light mode available.

### 8.1 `/` — Dashboard home

Eight-tile overview grid:

1. **Active Venue tile**: venue badge (KALSHI · DEMO), base URL, credentials green/red, last health check timestamp
2. **Pipeline tile**: last cycle, loop state (idle / running / stopped), aliases resolved count
3. **Freshness tile**: gauge bars for Kalshi snapshots, model predictions, settlement
4. **Today tile**: snapshots count, predictions count, paper bets (candidates / placed)
5. **Rolling CLV tile**: 100-bet and 500-bet rolling values with sparklines
6. **Open Exposure tile**: today's open exposure / bankroll, with per-day cap line
7. **Circuit Breaker tile**: green LED if OK, red with reason if tripped
8. **Live Trading tile**: red badge, "DISABLED — N gate conditions unmet", link to /live-trading

Below the grid: a "Recent Activity" feed pulling from `/api/v1/audit/operator-actions` and `/api/v1/bets`.

### 8.2 `/pipeline` — Pipeline control & state

- Hero: "Run cycle now" button. Triggers `POST /api/v1/pipeline/cycle`. Streams progress via WS into a per-node timeline.
- Loop control: input for interval-min, Start/Stop. Shows next-cycle countdown if loop active.
- Cycle history table: last 50 cycles with timing per node, outcome, errors.
- Freshness panel: gauges with green/yellow/red thresholds.

### 8.3 `/kalshi` — Kalshi integration

- Credentials Status banner: green if `kalshi/credentials/status` returns all set; red with config instructions otherwise.
- Health check button: pings `/api/v1/kalshi/health`, shows latency and clock skew.
- Tabs:
  - **Events**: paginated table of KXEPLTOTAL events with title, ticker, status, alias status (resolved / unresolved). Click → `/kalshi/events/[ticker]`.
  - **Markets**: searchable list filtered by floor_strike=2.5 by default.

#### `/kalshi/events/[ticker]`

- Event title, ticker, sub_title, category, status
- Resolved fixture (if any) with link
- Markets table for this event, with floor_strike column; OU 2.5 highlighted
- "Run bootstrap on this event" button — manual single-event bootstrap

#### `/kalshi/markets/[ticker]`

- Market detail: ticker, event_ticker, floor_strike, status
- Order book preview: yes_bid, yes_ask, no_bid, no_ask, sizes (live-updating via 5s polling, not WS since markets endpoint isn't streamed)
- Linked fixture + alias detail
- Recent odds snapshots chart for this market

### 8.4 `/aliases` — Alias management

- Filters: status, league, has-fixture, has-prediction
- Table: ticker, fixture_id, home/away teams, kickoff, prediction status, action menu (retire, view fixture)
- "Refresh aliases (run bootstrap)" button
- Link to `/aliases/create` for manual creation

#### `/aliases/create`

- Form: kalshi_event_ticker, fixture_id (autocomplete from upcoming fixtures), home_team_id, away_team_id (autocomplete from teams)
- Validates against existing fixture and shows preview before submit
- Submit → POST + redirect to alias detail

### 8.5 `/fixtures` — Fixture browser

- Filters: status, league, season, date range
- Table: fixture_id, league, kickoff, home/away, score (if final), alias count, prediction count
- Click → fixture detail

#### `/fixtures/[id]`

- Header: teams, kickoff, status, score
- Tabs:
  - **Overview**: rolling form features, recent matches, xG averages
  - **Aliases**: linked Kalshi events
  - **Predictions**: model predictions for this fixture across markets and model versions
  - **Bets**: paper bets placed on this fixture with full audit
  - **Snapshots**: odds snapshots timeline chart

### 8.6 `/predictions` — Predictions browser

- Filters: fixture, model version, date range
- Table: fixture, market, selection, p_raw, p_calibrated, sigma_p, model version, age
- Click → prediction detail

#### `/predictions/[id]`

- Header: fixture link, market, selection, model version, as_of timestamp
- Probability panel: p_raw vs p_calibrated, sigma_p, bootstrap CI
- Feature vector: named feature → value, with hover tooltip explaining each
- "Re-run for this fixture" button

### 8.7 `/bets` — Paper bets ledger

- Filters: status, fixture, venue, date range
- Table: fixture, market, selection, odds_taken, stake, edge_pct, Kelly fraction, settlement, CLV
- Sortable columns including CLV (descending shows best alpha)
- Click → bet detail

#### `/bets/[id]`

- Decision audit:
  - Prediction (link)
  - Edge math: `p_calibrated * odds - 1 - commission`
  - Kelly calc breakdown: p_lb, f_full, base_fraction, clv_multiplier, f_used, per_bet_cap, final stake
  - Quoted vs taken odds, slippage
  - Settlement: status, P&L
  - CLV: closing odds, CLV %, benchmark source (Kalshi close / Pinnacle / missing)
- Timeline: decided_at, placed_at, settlement_at

### 8.8 `/clv` — CLV analytics

- Rolling chart: 100-bet and 500-bet rolling CLV over time, with confidence band
- CLV histogram: distribution of per-bet CLV
- CLV by source: pie/bar showing Kalshi-close vs Pinnacle vs missing
- CLV by market: per-market mean CLV
- "Backfill CLV" button → modal with date range, confirmation, then job kickoff

### 8.9 `/risk` — Risk & bankroll

- Bankroll panel: current, peak, drawdown from peak, sparkline
- Exposure panel: open today, per-day cap, per-fixture exposure stacked bars
- Kelly preview tool: form with sliders for p_hat, sigma_p, odds, base_fraction. Live updates the calculated stake. Pure exploration tool; no side effects.
- Recent stakes histogram

### 8.10 `/warehouse` — Warehouse explorer

- Tables overview: list with row counts, last write
- Tabs / pages:
  - **Teams**: filterable list, click for team detail with fixtures and form
  - **Players**: paginated list (limited surface initially)
  - **Snapshots**: snapshots browser with filters

### 8.11 `/diagnostics` — System diagnostics

- Circuit breaker panel: state, last trip reason, reset button (with confirmation modal)
- Migrations: list with timestamps, names; green/red status
- Env: list of expected env vars with set/unset indicator (values never shown)

#### `/diagnostics/logs`

- Tail of recent logs, filterable by level, time range
- Auto-refresh every 5s when "Live" toggle is on
- Search within current view

### 8.12 `/audit` — Audit trail

- Operator actions: who, when, what
- Model version history: registered, promoted-to-production, retired
- Bet decisions audit: same as `/bets` but with extra metadata for compliance-style review

### 8.13 `/live-trading` — The gated page

- Big red banner at top: "LIVE TRADING IS DISABLED"
- Per-condition checklist from PROJECT_INSTRUCTIONS §3:
  - "✗ Positive CLV on 1000+ bets over 60+ days — current: N bets, M days, CLV X"
  - "✗ Operator has confirmed disposable bankroll — manual flag in env, not set"
- "Check conditions" button → re-runs the validation against the warehouse
- Documentation panel explaining what each condition means and why both are required
- NO enable button. Enabling is done in `.env` after both conditions are independently met.

### 8.14 `/settings` — Settings

- Theme: dark / light / system
- Density: comfortable / compact
- Default time range filters
- Default page sizes
- Credentials status (read-only) with link to SETUP_GUIDE.md
- Sign-out button

### 8.15 `/login`

- Single field: operator token
- Submit → POST `/api/v1/auth/login`, sets session cookie, redirects to `/`
- Shows generic error on failure; never reveals whether token-format-valid vs token-mismatch

---

## 9. Design System

### 9.1 Theme

Dark by default. Light supported. CSS variables driven by Tailwind config + next-themes.

Color tokens (these are the canonical palette; do not deviate):

```
--background:      hsl(220 14% 6%)         (dark) / hsl(0 0% 98%) (light)
--foreground:      hsl(210 20% 96%)        / hsl(220 14% 12%)
--card:            hsl(220 14% 8%)         / hsl(0 0% 100%)
--muted:           hsl(220 14% 14%)        / hsl(220 14% 94%)
--border:          hsl(220 14% 18%)        / hsl(220 14% 88%)
--accent:          hsl(160 60% 50%)        ← brand green (subtle, not loud)
--destructive:     hsl(0 70% 55%)
--warning:         hsl(40 90% 55%)
--success:         hsl(140 60% 50%)
--demo-pill:       hsl(220 80% 60%)        ← solid blue badge for "DEMO" venue
--production-pill: hsl(0 70% 55%)          ← solid red badge for "PRODUCTION" venue
```

Active venue pill is permanent in the topbar, color-coded. DEMO is calming blue; PRODUCTION is alarming red — a constant visual reminder.

### 9.2 Typography

- UI font: Inter (self-hosted)
- Monospace font: JetBrains Mono (self-hosted) — used for tickers, IDs, odds, prices, hex IDs, timestamps
- Numeric font feature: tabular-nums always on for table cells with numbers

### 9.3 Density

Default to "comfortable" but offer "compact" toggle. Compact reduces row height in tables, tightens padding. Operator preference persisted.

### 9.4 Components

Use shadcn/ui as the base. The components live in `components/ui/`. Required components at minimum:

`Button`, `Card`, `Dialog`, `DropdownMenu`, `Input`, `Label`, `Select`, `Tabs`, `Table`, `Toast` (via sonner), `Tooltip`, `Skeleton`, `Badge`, `Alert`, `AlertDialog` (for destructive confirmations), `Sheet` (slide-over panels), `Switch`, `Form` (rhf wrapper).

Add as needed: `Combobox`, `Calendar`, `Popover`, `Command` (cmd-k palette).

### 9.5 Layout

Persistent left sidebar with sections grouped:
- **Overview**: Home, Pipeline
- **Markets**: Kalshi, Aliases, Fixtures
- **Modeling**: Predictions, Bets, CLV
- **Operations**: Risk, Warehouse, Diagnostics, Audit
- **Settings**: Settings, Live Trading (visually distinct, red accent)

Topbar:
- Left: page title + breadcrumbs
- Right: cmd-k search trigger, theme toggle, venue pill, circuit-breaker LED, account menu

### 9.6 Tables

All large tables use TanStack Table headless. Features: column sorting, multi-column filter, pagination (server-side with offset+limit), column visibility toggle, column resize. Tables persist their state in URL query params so links are shareable.

### 9.7 Charts

Recharts is the primitive. Tremor components when available. Time-series charts default to:
- X axis: time, ISO short format
- Y axis: appropriate unit with prefix
- Zoom: brush at the bottom for time ranges
- Tooltip: rich, shows exact value + context

CLV charts use signed colors: positive = success-green, negative = destructive-red, with a baseline at zero.

### 9.8 Forms

react-hook-form + zod resolvers. Every form has client-side validation (zod) and server-side validation (FastAPI Pydantic). Mismatch shows as inline field error.

Destructive confirmations: AlertDialog with typed phrase confirmation. Example: "Type RETIRE-WHULEE to confirm retiring this alias."

### 9.9 Accessibility

All shadcn/ui components are Radix-based and accessible by default. Don't break their a11y. Color contrast meets WCAG AA. Keyboard navigation works across all interactive elements. cmd-k palette for power-user shortcuts.

---

## 10. Auth & Identity Model

Single operator. Single shared token stored in `.env` as `UI_OPERATOR_TOKEN`. Generated by:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Login flow:
1. Operator visits `/login`, enters token
2. Frontend POSTs to `/api/v1/auth/login`
3. Backend compares against env value (constant-time)
4. On match: backend signs a session JWT, sets it as HttpOnly + Secure + SameSite=Strict cookie
5. Subsequent API requests rely on the cookie
6. Cookie expires after 7 days of inactivity; sliding renewal

WebSocket auth: token from cookie passed as query param at handshake; same validation.

No session is "remembered" beyond the cookie. No password reset. No multi-factor (pointless for single-user single-token).

Server-side session table: a tiny SQLite file at `frontend/api/data/sessions.db` tracking active session IDs. On logout, the session ID is invalidated server-side too (not just cookie-deleted).

---

## 11. Real-time WebSocket Design

### 11.1 `/ws/v1/pipeline`

Server pushes events of the shape:

```json
{
  "type": "cycle_started" | "node_started" | "node_complete" | "cycle_finished" | "breaker_tripped" | "loop_status",
  "timestamp": "2026-05-12T14:23:45Z",
  "payload": {...}
}
```

Frontend subscribes when a cycle is in progress or when `/pipeline` is the active route. Otherwise WS is closed to save resources.

### 11.2 `/ws/v1/freshness`

Server pushes every 5 seconds (in active sessions) the current freshness map:

```json
{
  "type": "freshness_tick",
  "timestamp": "...",
  "payload": {
    "kalshi_snapshots": {"last_seen_at": "...", "age_seconds": 23},
    "model_predictions": {"last_seen_at": "...", "age_seconds": 480},
    ...
  }
}
```

Frontend uses this to drive live-updating freshness indicators on every page that shows them.

### 11.3 `/ws/v1/jobs/{job_id}`

Per-job progress for long-running operations (bootstrap, CLV backfill, batch prediction). Server pushes:

```json
{
  "type": "progress" | "log" | "completed" | "failed",
  "timestamp": "...",
  "payload": {"step": "...", "percent": 42, "message": "..."}
}
```

Frontend opens this WS when a job is started, closes on completion/failure.

### 11.4 Backpressure & reconnect

- Client: exponential backoff on disconnect (1s, 2s, 4s, 8s, max 30s)
- Client: drops messages older than 5s if rendering can't keep up
- Server: closes connections that don't pong within 60s
- Server: rate-limits push rate per connection

---

## 12. Build Stages

Implement in order. Each stage has explicit acceptance criteria. Do not start the next stage until the current one's criteria are met. Each stage commits its code on its own branch and pushes; PRs to main are not required for this single-operator setup but tags are: `frontend-stage-N-complete`.

### Stage 0 — Foundations

- Create `frontend/` folder, both subfolders, both `pyproject.toml` and `package.json`
- Wire dev experience: `pnpm dev` runs Next.js dev server on `:3000`; `uv run uvicorn footy_ev_api.main:app --reload --port 8000` runs FastAPI; Next.js rewrites `/api/v1/*` to `http://localhost:8000/api/v1/*` in dev
- ESLint, Prettier, Ruff, mypy all configured and passing on empty scaffolds
- Vitest, Playwright, pytest configured with passing example tests
- `frontend/README.md` written: how to run dev mode, how to run tests
- `frontend/.env.example` with `UI_OPERATOR_TOKEN`, `UI_API_BIND_HOST=127.0.0.1`, `UI_API_PORT=8000`, `UI_WEB_PORT=3000`

**Acceptance**: `pnpm dev` and uvicorn both run, browser shows a "hello world" Next.js page that successfully fetches `/api/v1/health` and renders the response. `pnpm test`, `pnpm test:e2e`, `pnpm lint`, `pnpm typecheck`, `uv run pytest`, `uv run mypy --strict src/`, `uv run ruff check` all green.

### Stage 1 — Auth & shell

- Implement `/api/v1/auth/*` endpoints
- Implement session middleware (JWT in HttpOnly cookie)
- Build `/login` page
- Build `AppShell`, `Sidebar`, `Topbar`, `VenuePill`, `CircuitBreakerLED`, theme toggle
- Wire layout: `app/layout.tsx` checks session on server, redirects to `/login` if missing (server component); `/login` is publicly accessible
- Implement `/api/v1/health` properly: includes version, uptime, env checks
- Implement `/api/v1/auth/me` for the topbar

**Acceptance**: navigating to `/` without a session redirects to `/login`. Successful login redirects to `/`. Wrong token shows error. Logout works. Topbar shows venue pill (placeholder data ok), circuit breaker LED, theme toggle.

### Stage 2 — API client + OpenAPI codegen

- Implement OpenAPI generation in FastAPI (versioned at `/api/v1/openapi.json`)
- Write `frontend/web/scripts/generate-api-types.ts` invoking `openapi-typescript` against `http://localhost:8000/api/v1/openapi.json` → `lib/api/types.gen.ts`
- Write typed `apiClient` wrapper around `fetch` with auth header, error envelope handling, request-id correlation
- Write TanStack Query hook factory pattern; provide hooks for `useHealth`, `useMe` as proof
- Add `pnpm types:gen` script

**Acceptance**: TypeScript types are auto-generated and used by `apiClient`. Adding a field to a FastAPI response Pydantic model + rerunning `pnpm types:gen` produces a TS error in the frontend until the rendering code consumes the field. Demonstrate this in a commit.

### Stage 3 — Pipeline control & state

- Implement `/api/v1/pipeline/*` endpoints, including WebSocket `/ws/v1/pipeline`
- Wire the existing `run.py cycle` invocation into the API as a backgrounded job; the JobManager owns running jobs
- Build `/pipeline` page: status section, "Run cycle now" button, loop control, freshness panel, cycle history table
- Build `useWebSocket` hook with reconnect/backoff
- WS payload drives a per-node timeline component during cycle execution

**Acceptance**: clicking "Run cycle now" produces visible WS events updating the node timeline. Loop start/stop persists across page reloads (server-side state). Freshness panel updates from `/ws/v1/freshness`.

### Stage 4 — Kalshi integration views

- Implement `/api/v1/kalshi/*` endpoints (read-only; auth-gated)
- Build `/kalshi` page with health-check button + tabs
- Build `/kalshi/events`, `/kalshi/events/[ticker]`, `/kalshi/markets/[ticker]`
- Build a per-event "Run bootstrap on this event" action (calls a single-event bootstrap)
- Credentials status banner driven by `/api/v1/kalshi/credentials/status`

**Acceptance**: against a live demo Kalshi connection, the event browser lists real events, market detail shows live YES/NO bid/ask, and the health check reports clock skew. Without credentials, the banner is red and informative.

### Stage 5 — Aliases & bootstrap UI

- Implement `/api/v1/aliases/*` and `/api/v1/bootstrap/*` endpoints
- Build `/aliases` page with filters, table, retire action (with typed confirmation)
- Build `/aliases/create` form with fixture autocomplete + preview-before-submit
- Build bootstrap UI: trigger button, mode toggle (live / fixture), job progress modal driven by `/ws/v1/jobs/{job_id}`
- Bootstrap history table

**Acceptance**: triggering a bootstrap from the UI produces aliases identical to running `python run.py bootstrap` from the CLI. The retire flow appends a status='retired' row without deleting. Manual alias creation rejects invalid fixture IDs.

### Stage 6 — Fixtures browser

- Implement `/api/v1/fixtures/*` endpoints
- Build `/fixtures` listing with filters and pagination
- Build `/fixtures/[id]` detail with tabs (Overview, Aliases, Predictions, Bets, Snapshots)

**Acceptance**: filters compose correctly and update the URL query string. Detail tabs lazy-load their data. Snapshot timeline chart renders.

### Stage 7 — Predictions browser

- Implement `/api/v1/predictions/*` endpoints
- Build `/predictions` listing with filters
- Build `/predictions/[id]` with probability panel + feature vector
- Build "Re-run predictions" action

**Acceptance**: re-running predictions from the UI produces rows identical to invoking the prediction node directly. Feature vector view is comprehensible and includes feature documentation tooltips.

### Stage 8 — Paper bets & CLV

- Implement `/api/v1/bets/*` and `/api/v1/clv/*` endpoints
- Build `/bets` ledger and `/bets/[id]` detail with full audit
- Build `/clv` analytics page with rolling chart, histogram, breakdown by source/market
- Build "Backfill CLV" action

**Acceptance**: rolling CLV chart matches values computed by a direct DuckDB query. Bet detail's Kelly breakdown is mathematically reproducible from the displayed inputs.

### Stage 9 — Risk & Kelly preview

- Implement `/api/v1/risk/*` endpoints including the pure-function Kelly preview
- Build `/risk` page: bankroll panel, exposure panel, Kelly preview tool
- The Kelly preview tool has sliders for each input and live updates the stake

**Acceptance**: Kelly preview matches `kelly_stake()` from the main project byte-for-byte across a battery of test inputs. Exposure panel respects per-day / per-fixture caps.

### Stage 10 — Warehouse explorer

- Implement `/api/v1/warehouse/*` endpoints, including the canned-query allowlist
- Build `/warehouse`, `/warehouse/teams`, `/warehouse/teams/[id]`, `/warehouse/players`, `/warehouse/snapshots`
- No raw SQL execution. All queries are in a versioned `frontend/api/src/footy_ev_api/queries/` directory and explicitly allowlisted

**Acceptance**: every row visible in the warehouse explorer can be reproduced by running a documented canned query from the queries directory. No way to execute arbitrary SQL through the UI.

### Stage 11 — Diagnostics & audit

- Implement `/api/v1/diagnostics/*` and `/api/v1/audit/*` endpoints
- Build `/diagnostics`, `/diagnostics/logs`, `/diagnostics/circuit-breaker`
- Build `/audit`
- Implement the operator-actions audit logging middleware (every state-mutating endpoint writes an audit row)

**Acceptance**: every mutating action across the app produces an audit row. Manual circuit breaker reset is logged. Log tail updates live when "Live" toggle is on.

### Stage 12 — Live trading gate page

- Implement `/api/v1/live-trading/*` endpoints (status + check-conditions only; no enable)
- Build `/live-trading` page with the prominent disabled banner and per-condition checklist
- Wire `check-conditions` button to a job that validates against the warehouse

**Acceptance**: visiting the page shows red banner. Conditions are checked accurately against the warehouse data. The page has no enable button. Attempting to set `LIVE_TRADING=true` via the API surface returns 405.

### Stage 13 — Polish, command palette, settings

- Implement cmd-k command palette: search across fixtures, aliases, bets, navigation
- Build `/settings` page
- Implement settings persistence (server-side, scoped to operator)
- Loading / empty / error states everywhere
- Skeleton loaders during data fetch
- Error boundaries with friendly recovery messaging
- Toast notifications for actions (sonner)
- Polish chart tooltips, table empty states

**Acceptance**: cmd-k works across the app. Every page handles loading, empty, and error states gracefully. No raw error stacks shown to user; they're logged server-side.

### Stage 14 — Testing pass

- Unit tests for utility functions (decimal formatters, date helpers, Kelly preview math reproduction)
- Component tests for at least three critical components (BetDetailAudit, KellyPreviewTool, CircuitBreakerLED with red/green states)
- E2E happy-path tests in Playwright:
  1. Login → dashboard renders
  2. Trigger pipeline cycle → completes with WS events visible
  3. Bootstrap → creates aliases visible in /aliases
  4. Browse a bet → audit numbers reconcile
  5. Live-trading page → check-conditions runs and shows N gate reasons
- Coverage threshold: 80% line coverage on `lib/`, components subjective

**Acceptance**: all tests green in CI (local CI is fine for this project). Add `pnpm test:e2e:headed` for the operator to watch tests run.

### Stage 15 — Documentation & deployment readiness

- Update `frontend/README.md` to cover: full architecture overview, local dev setup, deployment options (deferred but documented), troubleshooting
- Document the deployment path: how to build for production (`pnpm build`), how to run uvicorn with workers, how to put it behind nginx if desired
- Add a `docker-compose.yml` that runs FastAPI + Next.js in production mode (deferred to operator's choice)
- Update root `README.md` to point at the UI as the primary operator interface

**Acceptance**: a fresh checkout + `pnpm install && uv sync && pnpm dev` from `frontend/` brings up the full app within 5 minutes for someone following the README.

---

## 13. Testing Strategy

### 13.1 Backend

- Unit tests for adapters: mock the underlying `src/footy_ev/` functions, verify adapters call them with correct params
- API tests with FastAPI TestClient: verify request → response shapes match Pydantic schemas, errors match envelope, auth gates work
- Integration tests against a fixture DuckDB warehouse: warehouse routes return real data
- WebSocket tests: subscribe, trigger event, assert payload

### 13.2 Frontend

- Vitest + React Testing Library for component tests
- MSW (Mock Service Worker) to mock the API for component tests; real API client used, only the network is mocked
- Playwright for E2E flows
- Visual regression: optional; use Playwright's screenshot diffing if signal-vs-noise is worth it

### 13.3 Contract tests

- Build a contract test that boots both backend and frontend, walks through the OpenAPI schema, and verifies the FE types match what the BE returns for every endpoint. This catches drift between Pydantic models and TS types after manual edits.

---

## 14. Local Development Setup

`frontend/scripts/dev.sh`:

```bash
#!/usr/bin/env bash
# Launches FastAPI + Next.js dev servers concurrently.
# Reads .env from frontend/.env.
set -euo pipefail
cd "$(dirname "$0")/.."

# Source env
set -a; source .env; set +a

# FastAPI
( cd api && uv run uvicorn footy_ev_api.main:app --reload --host "${UI_API_BIND_HOST:-127.0.0.1}" --port "${UI_API_PORT:-8000}" ) &
API_PID=$!

# Next.js
( cd web && pnpm dev --port "${UI_WEB_PORT:-3000}" ) &
WEB_PID=$!

trap "kill $API_PID $WEB_PID" EXIT
wait
```

Equivalent PowerShell at `frontend/scripts/dev.ps1` for Windows-first operator.

`run.py` updates: add `ui` subcommand that invokes `frontend/scripts/dev.ps1`, so `uv run python run.py ui` launches both servers and opens the browser to `http://localhost:3000`.

### 14.1 First-run checklist (documented in README)

1. `cd frontend && cp .env.example .env`
2. Generate operator token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
3. Edit `.env` and paste the token into `UI_OPERATOR_TOKEN=`
4. `cd api && uv sync`
5. `cd ../web && pnpm install`
6. From repo root: `uv run python run.py ui`
7. Open browser to `http://localhost:3000`, paste token at `/login`

---

## 15. Deployment (deferred)

Document the deployment path even though it's not built in this scope:

- Production build: `cd web && pnpm build && pnpm start` runs the Next.js production server on `:3000`
- FastAPI in production: uvicorn with `--workers 2`, behind nginx with TLS termination if remote
- `docker-compose.yml` builds both, runs both, exposes only the frontend port externally if remote, with the FastAPI behind the internal docker network
- Oracle Cloud Free Tier or DigitalOcean (Student credit) are viable targets per PROJECT_INSTRUCTIONS

Defer the actual deployment until paper trading on Kalshi demo accumulates enough history that remote 24/7 polling is genuinely valuable.

---

## 16. Banned Approaches

- **No raw SQL execution endpoint in the UI**, ever. Allowlisted canned queries only.
- **No endpoint to set `LIVE_TRADING=true`**. Live trading enable is `.env` only, after independent Phase 4 validation.
- **No persisting of Kalshi credentials in the UI database or settings.** Credentials are env-only.
- **No client-side trust of decimal math**. Convert via `decimal.js` on the FE; backend always returns strings for monetary values.
- **No floats for money in API contracts**. Strings.
- **No third-party analytics, tracking pixels, fonts from external CDNs (unless self-hosted is explicitly disabled by operator)**.
- **No external auth providers (Google OAuth, etc.)**. Single-operator-token only.
- **No abandoning the audit-trail middleware** under the excuse of "this action is trivial." Every mutation logs.
- **No breaking `mypy --strict` on the backend** or `tsc --noEmit` strict on the frontend.
- **No catch-and-swallow on API errors**. Frontend toast notification on every failure with the backend's `request_id` for correlation.

---

## 17. Definition of Done per Stage

Each stage is done when:

1. All code in the stage's scope is committed and pushed
2. `pnpm typecheck`, `pnpm lint`, `pnpm test` all green on the frontend
3. `uv run mypy --strict src/`, `uv run ruff check`, `uv run pytest` all green on the backend
4. The stage's specific acceptance criteria (see §12) are demonstrated
5. The README in `frontend/` is updated if the stage changes setup, ops, or features the operator interacts with
6. Tagged in git: `frontend-stage-N-complete`

---

## 18. Module-level Acceptance Criteria

The frontend module is ready for daily operator use when:

- [ ] All 15 stages complete
- [ ] Operator can perform every action previously available in `run.py` through the UI
- [ ] Every state previously visible only via direct DuckDB queries is surfaced in the UI
- [ ] Auth works end-to-end with a single operator token from `.env`
- [ ] Every mutation produces an audit row
- [ ] Circuit breaker state is always visible and reset requires confirmation
- [ ] Live trading gate page exists, never enables, and explains its refusal
- [ ] `pnpm build` produces a working production bundle
- [ ] First-run checklist gets a new operator from clone to working UI in <10 minutes
- [ ] No raw secrets ever cross the API boundary
- [ ] Both `mypy --strict` and `tsc --noEmit` pass cleanly across the module

---

## 19. Pointers to Main Project Files

When implementing each stage, the agent should read these for context:

- `CLAUDE.md` — operating rules, banned paths, conventions
- `README.md` — current overall state
- `PROJECT_INSTRUCTIONS.md` §3 (bankroll), §5 (banned paths), §6 (rigor), §7 (execution policy)
- `BLUE_MAP.md` §1 (failure modes), §2 (orchestration), §4 (risk math), §6 (warehouse schema), §7 (validation)
- `HANDOFF.md` — latest state notes
- `src/footy_ev/venues/kalshi.py` — auth model, response shapes, OU 2.5 filter
- `src/footy_ev/orchestration/` — pipeline nodes that the API wraps
- `src/footy_ev/runtime/paper_trader.py` — for understanding how the existing CLI orchestrates
- `src/footy_ev/db/schema.sql` — canonical table definitions

---

## 20. Open Questions to Decide Later (do not block on these)

These are deferred design questions the operator will weigh in on closer to the relevant stage. The agent should make reasonable defaults that match the rest of the plan but call these out in the relevant stage's report:

1. **Theme**: dark-by-default is locked. Should light mode actually be tested or is dark the only one we polish?
2. **Mobile**: best-effort responsive, not mobile-optimized. Acceptable to skip mobile-specific layouts entirely?
3. **Time zones**: render everything in UTC vs operator's local time. Default to UTC with hover-tooltip showing local; flag if a stage hits a workflow where this is awkward.
4. **Currency display**: bets are GBP-denominated in the schema but Kalshi is USD. Surface both? Convert? Pick GBP as canonical and label clearly?
5. **Export**: should tables have a "Download CSV" affordance? Defer to stage 13 (polish) and add if it's clearly useful.
6. **Concurrency on jobs**: only one pipeline cycle at a time? Multiple bootstrap jobs allowed? Default: serialize all mutating jobs into a single queue; pipeline cycles can't overlap but read endpoints work concurrently.
7. **Schema changes the UI implies**: an `operator_actions` audit table is new and lives in the main warehouse. Add via a `migration_013_operator_actions.sql` in the main project as part of stage 11. Surface this dependency early.

These get resolved as the relevant stage ships. None are blockers for starting.
