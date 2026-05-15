# footy-ev Frontend — Quick Start Guide

Complete guide to running the full footy-ev stack from a fresh terminal on Windows 11.

---

## Prerequisites

| Tool | Required | Install |
|---|---|---|
| Python 3.12+ | Required | [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.12` |
| [uv](https://docs.astral.sh/uv/) | Required | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Node.js 20 LTS | Required | [nodejs.org](https://nodejs.org/) or `winget install OpenJS.NodeJS.LTS` |
| [pnpm](https://pnpm.io/) | Required | `npm install -g pnpm` |

Verify everything is installed:

```powershell
python --version    # Python 3.12.x
uv --version        # uv 0.x.x
node --version      # v20.x.x
pnpm --version      # 9.x.x or 8.x.x
```

---

## First-time Setup

Run these commands once from the `footy-ev` project root:

```powershell
# 1. Create the frontend .env from the example
cd frontend
Copy-Item .env.example .env

# 2. Generate a random operator token
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy the output, then open frontend/.env and paste it as:
# UI_OPERATOR_TOKEN=<your-token-here>

# 3. Install backend (FastAPI) dependencies
cd api
uv sync
cd ..

# 4. Install frontend (Next.js) dependencies
cd web
pnpm install
cd ..
```

The `.env` file lives at `frontend/.env` and is gitignored. Never commit it.

---

## Starting Everything

### Option A — single command (recommended)

From the **project root** (`footy-ev/`):

```powershell
uv run python run.py ui
```

This runs `frontend/scripts/dev.ps1`, which starts both servers concurrently:
- **FastAPI backend** on `http://127.0.0.1:8000`
- **Next.js dev server** on `http://localhost:3000`

Press `Ctrl+C` to stop both.

### Option B — two separate terminals

**Terminal 1 — FastAPI backend:**

```powershell
cd footy-ev\frontend\api
uv run uvicorn footy_ev_api.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — Next.js frontend:**

```powershell
cd footy-ev\frontend\web
pnpm dev
```

---

## Accessing the UI

1. Open **http://localhost:3000** in your browser.
2. You will be redirected to `/login`.
3. Paste your `UI_OPERATOR_TOKEN` (from `frontend/.env`) into the token field.
4. Click **Sign in**. You will be redirected to the dashboard.

First load shows the pipeline health indicator and freshness gauges. If the backend is not running, you will see a connection error.

**API docs (Swagger UI):** http://localhost:8000/docs

---

## Running the Main Pipeline Alongside the UI

The FastAPI backend is a **read-only** view layer over the warehouse. You can run pipeline commands from a third terminal while both UI servers are running:

```powershell
# Check pipeline status (no API calls, warehouse-only)
uv run python run.py status

# Run one pipeline cycle (scrape → price → risk → place paper bets)
uv run python run.py cycle

# Start continuous loop (every 15 minutes)
uv run python run.py loop --interval-min 15

# Refresh Kalshi event aliases
uv run python run.py bootstrap
```

The UI polls the warehouse via FastAPI and will reflect new bets and predictions as they appear — no restart needed.

---

## Stopping Everything

- **Option A** (`run.py ui`): press `Ctrl+C` once. Both processes are terminated.
- **Option B** (separate terminals): press `Ctrl+C` in each terminal.

The FastAPI and Next.js dev servers have no persistent state; stopping them is always safe.

---

## Troubleshooting

### Port already in use

```
Error: listen EADDRINUSE :::3000
```

Another process is using port 3000 (or 8000). Kill it:

```powershell
# Find and kill the process holding port 3000
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

Or change the port in `frontend/.env`:

```
UI_WEB_PORT=3001
UI_API_PORT=8001
```

### Missing environment variables

The API will refuse to start if `UI_OPERATOR_TOKEN` is not set. Verify `frontend/.env` exists and contains the token:

```powershell
Get-Content frontend\.env
```

If the file is missing, re-run the first-time setup steps above.

### DuckDB locked by another process

```
duckdb.duckdb.IOException: Could not set lock on file
```

Only one process can write to `data/warehouse/footy_ev.duckdb` at a time. Check for a running pipeline:

```powershell
Get-Process -Name python -ErrorAction SilentlyContinue
```

Stop any background pipeline processes before starting the API with write access. The API uses `read_only=True` for most operations, so it can coexist with a pipeline reading the same database — but a DuckDB write lock from a pipeline cycle will block the API momentarily.

### pnpm: command not found

```
pnpm : The term 'pnpm' is not recognized
```

Install pnpm globally:

```powershell
npm install -g pnpm
```

Then close and re-open your terminal so the PATH update takes effect.

### uv: command not found

```
uv : The term 'uv' is not recognized
```

Install uv:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then close and re-open your terminal.

### Next.js build errors after pnpm install

```
Module not found: ...
```

Delete the build cache and reinstall:

```powershell
cd frontend\web
Remove-Item -Recurse -Force .next, node_modules
pnpm install
pnpm dev
```

### Backend 500 errors on first run

The warehouse DuckDB file may not exist yet. Run at least one pipeline cycle first:

```powershell
uv run python run.py status
```

This creates the database with the correct schema. The FastAPI backend applies migrations at startup, so subsequent runs are safe.

---

## Running Tests

```powershell
# Backend (FastAPI)
cd frontend\api
uv run pytest

# Frontend (Next.js + Vitest)
cd frontend\web
pnpm test

# Type checking
cd frontend\api && uv run mypy --strict src/
cd frontend\web && pnpm typecheck

# Linting
cd frontend\api && uv run ruff check src/
cd frontend\web && pnpm lint
```
