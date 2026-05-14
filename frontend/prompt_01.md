Read frontend/PLAN.md in full. This is the source of truth for the entire frontend module build.

You are implementing Stage 0 — Foundations. This stage creates the folder structure, wires both dev servers, configures all tooling, and proves the FE→BE connection works end-to-end with a health endpoint.

Platform: Windows 11 / PowerShell 5.1. All scripts must work in PowerShell. Provide a .ps1 dev script, not .sh.

## What to create

### 1. Folder structure

Create the full directory tree specified in PLAN.md §5. Every folder, every __init__.py. Don't create placeholder files for stages 1–15 code — only the folders and __init__.py files that the package structure requires.

### 2. Backend scaffold: frontend/api/

pyproject.toml with:
- name = "footy-ev-api"
- python = ">=3.12"
- Dependencies per PLAN.md §6.1: fastapi ^0.115, uvicorn[standard] ^0.32, pydantic ^2.9, pydantic-settings ^2.6, httpx ^0.27, python-jose[cryptography] ^3.3, websockets ^13.1, duckdb (match main project version from root pyproject.toml)
- Dev deps: pytest ^8.3, pytest-asyncio ^0.24, mypy ^1.13, ruff (latest)
- Editable install of the main project: add `footy-ev = {path = "../../", develop = true}` so `from footy_ev import ...` works from the API code

src/footy_ev_api/__init__.py with version string.

src/footy_ev_api/main.py — FastAPI app factory:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def create_app() -> FastAPI:
    app = FastAPI(
        title="footy-ev API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api/v1")
    return app

app = create_app()
```

src/footy_ev_api/routers/__init__.py — empty.

src/footy_ev_api/routers/health.py:
```python
from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(tags=["health"])
_started_at = datetime.now(timezone.utc)

@router.get("/health")
async def health():
    uptime = (datetime.now(timezone.utc) - _started_at).total_seconds()
    return {"status": "ok", "version": "0.1.0", "uptime_s": round(uptime, 1)}
```

src/footy_ev_api/settings.py — Pydantic Settings stub:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ui_operator_token: str = ""
    ui_api_bind_host: str = "127.0.0.1"
    ui_api_port: int = 8000
    ui_web_port: int = 3000
    warehouse_path: str = "../../data/footy_ev.duckdb"

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}
```

tests/ with a single passing test:
```python
from fastapi.testclient import TestClient
from footy_ev_api.main import create_app

def test_health():
    client = TestClient(create_app())
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

Ruff config in pyproject.toml: same rules as the main project.
mypy config: strict = true.

### 3. Frontend scaffold: frontend/web/

Initialize with: `pnpm create next-app@latest web --typescript --tailwind --eslint --app --src-dir=no --import-alias="@/*" --no-turbopack`

Then configure:

package.json scripts:
```json
{
  "scripts": {
    "dev": "next dev --port 3000",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test",
    "test:e2e:headed": "playwright test --headed",
    "types:gen": "echo 'OpenAPI codegen wired in stage 2'"
  }
}
```

Install additional deps per PLAN.md §6.2:
```
pnpm add @tanstack/react-query @tanstack/react-table zustand react-hook-form zod @hookform/resolvers recharts @tremor/react lucide-react clsx tailwind-merge next-themes sonner decimal.js date-fns
pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom @playwright/test prettier prettier-plugin-tailwindcss msw
```

Install shadcn/ui: `npx shadcn@latest init` with:
- Style: default
- Base color: slate
- CSS variables: yes
- Tailwind CSS: yes
- Components path: @/components/ui
- Utils path: @/lib/utils

Then add initial components: `npx shadcn@latest add button card`

next.config.ts — add API rewrite for dev:
```typescript
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://localhost:8000/api/v1/:path*',
      },
    ];
  },
};

export default nextConfig;
```

tailwind.config.ts — extend with the color tokens from PLAN.md §9.1. Set dark mode to "class" for next-themes.

app/globals.css — add CSS variables for both light and dark themes per PLAN.md §9.1 color tokens.

app/layout.tsx — basic layout with Inter font (from next/font/google), html lang="en", dark class by default.

app/page.tsx — a simple page that:
- Fetches /api/v1/health on mount (client component with useEffect or TanStack Query)
- Renders: "footy-ev" heading, the health response JSON (status, version, uptime), and a green "API Connected" badge if successful, red "API Unreachable" if failed
- Styled with Tailwind, dark background, the project's color tokens

vitest.config.ts:
```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, '.') },
  },
});
```

tests/setup.ts: import @testing-library/jest-dom.

tests/unit/health.test.tsx: render the home page with a mocked fetch, assert "API Connected" text appears.

playwright.config.ts: base URL localhost:3000, webServer command for dev.

.eslintrc.json: extend next/core-web-vitals + next/typescript.

prettier.config.mjs: singleQuote true, tailwindcss plugin.

tsconfig.json: strict true, paths alias @/* → ./*.

### 4. Dev scripts

frontend/scripts/dev.ps1:
```powershell
# Launches FastAPI + Next.js dev servers concurrently.
$ErrorActionPreference = "Stop"

# Load .env
if (Test-Path "$PSScriptRoot/../.env") {
    Get-Content "$PSScriptRoot/../.env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
        }
    }
}

$apiHost = if ($env:UI_API_BIND_HOST) { $env:UI_API_BIND_HOST } else { "127.0.0.1" }
$apiPort = if ($env:UI_API_PORT) { $env:UI_API_PORT } else { "8000" }
$webPort = if ($env:UI_WEB_PORT) { $env:UI_WEB_PORT } else { "3000" }

Write-Host "Starting FastAPI on ${apiHost}:${apiPort}..."
$api = Start-Process -NoNewWindow -PassThru -FilePath "uv" `
    -ArgumentList "run","uvicorn","footy_ev_api.main:app","--reload","--host",$apiHost,"--port",$apiPort `
    -WorkingDirectory "$PSScriptRoot/../api"

Write-Host "Starting Next.js on localhost:${webPort}..."
$web = Start-Process -NoNewWindow -PassThru -FilePath "pnpm" `
    -ArgumentList "dev","--port",$webPort `
    -WorkingDirectory "$PSScriptRoot/../web"

Write-Host ""
Write-Host "=== footy-ev UI ==="
Write-Host "Frontend: http://localhost:${webPort}"
Write-Host "API docs: http://localhost:${apiPort}/docs"
Write-Host "Press Ctrl+C to stop both."
Write-Host "==================="

try {
    Wait-Process -Id $api.Id, $web.Id
} finally {
    if (!$api.HasExited) { Stop-Process -Id $api.Id -Force }
    if (!$web.HasExited) { Stop-Process -Id $web.Id -Force }
}
```

### 5. Env files

frontend/.env.example:
```
UI_OPERATOR_TOKEN=generate-with-python-secrets-token-urlsafe-32
UI_API_BIND_HOST=127.0.0.1
UI_API_PORT=8000
UI_WEB_PORT=3000
```

frontend/.gitignore:
```
web/node_modules/
web/.next/
web/out/
api/.venv/
api/data/
.env
*.pyc
__pycache__/
```

### 6. Update root run.py

Add a `ui` subcommand to run.py that invokes the dev script:

```python
elif args.command == "ui":
    import subprocess
    script = Path("frontend/scripts/dev.ps1")
    if not script.exists():
        print("Frontend not installed. See frontend/README.md.")
        sys.exit(1)
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)], check=True)
```

Wire it into the argparse subparsers alongside cycle/loop/dashboard/status/bootstrap.

### 7. frontend/README.md

Write a README covering:
- What this is (frontend module for footy-ev, Stage 0)
- Prerequisites (Node 20+, pnpm, uv, Python 3.12+)
- First-run setup (copy .env, generate token, uv sync, pnpm install)
- How to run dev mode (dev.ps1 or `uv run python run.py ui` from root)
- How to run tests (backend and frontend separately)
- Current state: Stage 0 complete, health endpoint only
- Link to PLAN.md for the full build plan

## Acceptance criteria (verify all before committing)

1. From frontend/api/: `uv sync` succeeds, `uv run uvicorn footy_ev_api.main:app --port 8000` starts, `curl http://localhost:8000/api/v1/health` returns `{"status":"ok",...}`
2. From frontend/web/: `pnpm install` succeeds, `pnpm dev` starts on :3000, browser shows the health-check page with "API Connected" when API is running
3. `uv run pytest` in frontend/api/ — 1 test passes
4. `pnpm test` in frontend/web/ — 1 test passes
5. `uv run mypy --strict src/` in frontend/api/ — clean
6. `pnpm typecheck` in frontend/web/ — clean
7. `pnpm lint` in frontend/web/ — clean
8. `uv run ruff check src/` in frontend/api/ — clean
9. From project root: `uv run python run.py ui` launches both servers

## Commits

1. `feat(frontend): folder structure + api pyproject.toml + web package.json`
2. `feat(frontend/api): FastAPI health endpoint + settings + test`
3. `feat(frontend/web): Next.js scaffold with Tailwind + shadcn + health page`
4. `feat(frontend): dev.ps1 launcher + .env.example`
5. `feat: run.py ui subcommand`
6. `docs(frontend): README.md for Stage 0`
7. `chore: tag frontend-stage-0-complete`

Push at end. All acceptance criteria verified before the tag commit.

## Summary checkpoint (include in your report)

After all commits, report:
a. Both servers start and connect — verified yes/no
b. Health endpoint response shape
c. Frontend renders with correct color tokens from PLAN.md §9.1
d. Test counts: backend and frontend separately
e. mypy --strict and tsc --noEmit both clean: yes/no
f. Any dependency resolution issues encountered and how resolved
g. Any deviations from the plan, with justification
