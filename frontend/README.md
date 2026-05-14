# footy-ev Frontend Module

Operator-facing web UI for the footy-ev betting pipeline. FastAPI backend + Next.js frontend, isolated in `frontend/` so the main pipeline runs independently.

**Current state: Stage 0 complete.** Health endpoint only. See [PLAN.md](PLAN.md) for the full 15-stage build plan.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+ (LTS recommended)
- [pnpm](https://pnpm.io/) (Node package manager)

## First-run setup

```powershell
# 1. Create your .env from the example
cd frontend
Copy-Item .env.example .env

# 2. Generate an operator token and paste it into .env
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

## Running dev mode

**Option A** (recommended): from the project root:

```powershell
uv run python run.py ui
```

This launches both servers via `frontend/scripts/dev.ps1`.

**Option B**: run servers separately:

```powershell
# Terminal 1: FastAPI backend
cd frontend/api
uv run uvicorn footy_ev_api.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: Next.js frontend
cd frontend/web
pnpm dev
```

Open http://localhost:3000 in your browser. The health-check page will show "API Connected" when the backend is running.

API docs (Swagger UI): http://localhost:8000/docs

## Running tests

```powershell
# Backend
cd frontend/api
uv run pytest

# Frontend
cd frontend/web
pnpm test
```

## Type checking and linting

```powershell
# Backend
cd frontend/api
uv run mypy --strict src/
uv run ruff check src/

# Frontend
cd frontend/web
pnpm typecheck
pnpm lint
```

## Architecture

- `api/` -- FastAPI backend (Python). Imports from `src/footy_ev/` via editable install. Thin transport layer over existing pipeline logic.
- `web/` -- Next.js 16 + React 19 + TypeScript + Tailwind CSS v4 + shadcn/ui. Dev server proxies `/api/v1/*` to the FastAPI backend.
- `scripts/dev.ps1` -- PowerShell launcher that starts both servers concurrently.

See [PLAN.md](PLAN.md) for the complete build plan, API surface, page designs, and design system.
