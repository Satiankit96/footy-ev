# footy-ev Frontend Module

Operator-facing web UI for the footy-ev betting pipeline. **All 15 stages complete.**

The UI replaces `run.py` as the daily operator interface: browse fixtures, predictions, and bets; trigger pipeline cycles; inspect CLV; manage Kalshi event aliases; and monitor the live-trading gate conditions — all through a browser rather than a terminal.

---

## Architecture

```
Browser (localhost:3000)
  └── Next.js 16 + React 19 + TypeScript + Tailwind CSS v4
       └── proxies /api/v1/* → FastAPI (localhost:8000)
            └── Python 3.12 + FastAPI + Pydantic v2
                 └── reads/writes DuckDB warehouse (data/footy_ev.duckdb)
                 └── imports src/footy_ev/ via editable install
```

**`api/`** — FastAPI backend. Thin HTTP/WebSocket transport layer over existing `src/footy_ev/` pipeline code. Exposes 48 REST endpoints and 3 WebSocket channels.

**`web/`** — Next.js frontend. App Router, React 19, TypeScript strict mode. Dev server proxies `/api/v1/*` to the FastAPI backend. API types are auto-generated from FastAPI's OpenAPI spec.

**Communication patterns:**
- REST (JSON) for all data fetching and mutations. API types generated via `openapi-typescript`.
- WebSocket for live pipeline events (`/ws/v1/pipeline`), freshness heartbeat (`/ws/v1/freshness`), and long-running job progress (`/ws/v1/jobs/{job_id}`).
- HttpOnly session cookie for auth (set by `/api/v1/auth/login`, validated by Next.js middleware).

**State management:**
- TanStack Query — server state (caching, background refetch, optimistic updates).
- Zustand — client state (settings preferences synced from `/settings` on load).
- URL query params — filter/pagination state (shareable links).

---

## Quick Start

Full step-by-step guide: **[QUICKSTART.md](QUICKSTART.md)**

**TL;DR** (after first-time setup):

```powershell
# From the footy-ev project root
uv run python run.py ui
```

Open http://localhost:3000 and log in with your `UI_OPERATOR_TOKEN`.

---

## First-Run Setup

```powershell
# 1. Create your .env from the example
cd frontend
Copy-Item .env.example .env

# 2. Generate an operator token and paste it into .env as UI_OPERATOR_TOKEN=<token>
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 3. Install backend dependencies
cd api
uv sync
cd ..

# 4. Install frontend dependencies
cd web
pnpm install
cd ..
```

---

## Development Commands

### Backend (`frontend/api/`)

```powershell
# Start FastAPI dev server (auto-reload)
uv run uvicorn footy_ev_api.main:app --reload --host 127.0.0.1 --port 8000

# Run tests
uv run pytest

# Type checking (strict)
uv run mypy --strict src/

# Linting + format check
uv run ruff check src/
uv run ruff format --check src/
```

### Frontend (`frontend/web/`)

```powershell
# Start Next.js dev server
pnpm dev

# Run unit tests (Vitest)
pnpm test

# Run unit tests in watch mode
pnpm test:watch

# Run E2E tests (Playwright — requires both servers running)
pnpm test:e2e

# Run E2E tests in headed mode (watch the browser)
pnpm test:e2e:headed

# Type checking (strict)
pnpm typecheck

# Linting
pnpm lint

# Regenerate API types from OpenAPI spec (requires API on :8000)
pnpm types:gen

# Production build
pnpm build
pnpm start
```

---

## Project Structure

```
frontend/
├── PLAN.md                  ← full 15-stage build plan + API surface
├── README.md                ← this file
├── QUICKSTART.md            ← first-run Windows 11 guide
├── PROGRESS.md              ← full build history + stage summaries
├── docker-compose.yml       ← production-mode compose (both services)
├── .env.example             ← UI env vars (copy to .env)
│
├── api/                     ← FastAPI backend
│   ├── pyproject.toml
│   ├── src/footy_ev_api/
│   │   ├── main.py          ← app factory + router registration
│   │   ├── auth.py          ← JWT cookie middleware
│   │   ├── deps.py          ← dependency injection
│   │   ├── errors.py        ← error envelope + handlers
│   │   ├── adapters/        ← thin wrappers over src/footy_ev/
│   │   ├── routers/         ← FastAPI route handlers
│   │   └── schemas/         ← Pydantic request/response models
│   └── tests/
│
└── web/                     ← Next.js frontend
    ├── app/
    │   ├── (dashboard)/     ← all authenticated pages
    │   │   ├── layout.tsx   ← AppShell + ErrorBoundary wrapper
    │   │   ├── page.tsx     ← dashboard overview (/)
    │   │   ├── pipeline/    ← /pipeline
    │   │   ├── kalshi/      ← /kalshi (+ events, markets)
    │   │   ├── aliases/     ← /aliases (+ create)
    │   │   ├── fixtures/    ← /fixtures (+ [id])
    │   │   ├── predictions/ ← /predictions (+ [id])
    │   │   ├── bets/        ← /bets (+ [id])
    │   │   ├── clv/         ← /clv
    │   │   ├── risk/        ← /risk
    │   │   ├── warehouse/   ← /warehouse (+ teams, players, snapshots)
    │   │   ├── diagnostics/ ← /diagnostics (+ logs)
    │   │   ├── audit/       ← /audit
    │   │   ├── live-trading/← /live-trading
    │   │   └── settings/    ← /settings
    │   └── login/           ← /login (public)
    ├── components/
    │   ├── ui/              ← shadcn/ui components (copy-pasted, operator-owned)
    │   ├── layout/          ← AppShell, Sidebar, Topbar, VenuePill, CircuitBreakerLED
    │   ├── command-palette.tsx ← Ctrl+K search palette
    │   └── error-boundary.tsx  ← React class error boundary + withErrorBoundary HOC
    ├── lib/
    │   ├── api/
    │   │   ├── client.ts    ← typed fetch wrapper (ApiError, apiClient)
    │   │   ├── v1.gen.ts    ← auto-generated OpenAPI types (don't edit)
    │   │   ├── ws.ts        ← useWebSocket hook with backoff
    │   │   └── hooks/       ← TanStack Query hooks per domain
    │   ├── stores/
    │   │   └── settings.ts  ← Zustand settings store
    │   └── utils/
    │       └── format.ts    ← formatTimestamp, formatAge, formatClv, clvColor
    └── tests/
        ├── unit/            ← Vitest + React Testing Library
        └── e2e/             ← Playwright (5 flows)
```

---

## API Documentation

With the backend running:

- **Swagger UI:** http://localhost:8000/docs — interactive API explorer, requires operator token
- **ReDoc:** http://localhost:8000/redoc — readable reference
- **OpenAPI JSON:** http://localhost:8000/openapi.json — raw spec, used by `pnpm types:gen`

---

## Stage Status

| Stage | Name | Status |
|---|---|---|
| 0 | Foundations | Complete |
| 1 | Auth & Shell | Complete |
| 2 | API Client + OpenAPI Codegen | Complete |
| 3 | Pipeline Control & State | Complete |
| 4 | Kalshi Integration Views | Complete |
| 5 | Aliases & Bootstrap UI | Complete |
| 6 | Fixtures Browser | Complete |
| 7 | Predictions Browser | Complete |
| 8 | Paper Bets & CLV | Complete |
| 9 | Risk & Kelly Preview | Complete |
| 10 | Warehouse Explorer | Complete |
| 11 | Diagnostics & Audit | Complete |
| 12 | Live Trading Gate Page | Complete |
| 13 | Polish, Command Palette, Settings | Complete |
| 14 | Testing Pass | Complete |
| 15 | Documentation & Deployment Readiness | **Complete** |

---

## Deployment (Deferred — Documented Here for When It's Needed)

The frontend currently runs in local dev mode. Deployment to a remote host (Oracle Cloud Free Tier or DigitalOcean Student credit) is deferred until 60+ days of demo paper trading validate the system.

### Production Build (Local)

```powershell
# Build Next.js for production
cd frontend/web
pnpm build
pnpm start            # runs on :3000

# Run FastAPI in production mode
cd frontend/api
uv run uvicorn footy_ev_api.main:app --host 127.0.0.1 --port 8000 --workers 2
```

### Docker Compose

A `docker-compose.yml` is included at `frontend/docker-compose.yml`. It runs both services in production mode:

```powershell
cd frontend
docker-compose up --build
```

Services:
- `api` — FastAPI + uvicorn on port 8000 (internal only)
- `web` — Next.js production server on port 3000 (mapped to host)

Set environment variables in a `frontend/.env` file before running (see `.env.example`).

### nginx TLS Termination Sketch (Remote Deployment)

When deploying to a remote VPS, put nginx in front:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.example.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain/privkey.pem;

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API + WebSocket
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Run FastAPI with `--host 0.0.0.0` when behind nginx, and set `UI_API_BIND_HOST=0.0.0.0` in `.env`.

---

## Troubleshooting

See [QUICKSTART.md — Troubleshooting section](QUICKSTART.md#troubleshooting) for the full guide. Common issues:

| Symptom | Fix |
|---|---|
| Port 3000/8000 in use | `netstat -ano \| findstr :3000` → `taskkill /PID <PID> /F` |
| API refuses to start | Check `frontend/.env` has `UI_OPERATOR_TOKEN=` set |
| DuckDB lock error | Stop other Python processes; API uses `read_only=True` for most ops |
| `pnpm` not found | `npm install -g pnpm`, restart terminal |
| `uv` not found | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"`, restart terminal |
| Module not found after `pnpm install` | `Remove-Item -Recurse -Force .next, node_modules && pnpm install` |
| 500 errors on first run | Run `uv run python run.py status` first (creates warehouse schema) |
| `pnpm types:gen` fails | Ensure FastAPI is running on `:8000` first |
| E2E tests time out | Ensure both servers are running; or run via `pnpm test:e2e` (auto-starts Next.js) |
