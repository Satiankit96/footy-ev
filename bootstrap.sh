#!/usr/bin/env bash
# bootstrap.sh — one-shot scaffold for the footy-ev project (free-tier edition)
# Usage: bash bootstrap.sh [project_dir]
#   defaults to ./footy-ev if no arg given

set -euo pipefail

PROJECT_DIR="${1:-footy-ev}"
PROJECT_NAME="footy-ev"
PYTHON_VERSION="3.12"

echo "==> Bootstrapping ${PROJECT_NAME} in ${PROJECT_DIR}/ (free-tier edition)"

# --- Pre-flight checks -------------------------------------------------------
command -v uv >/dev/null 2>&1 || {
    echo "ERROR: uv is not installed. Install via:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
}
command -v git >/dev/null 2>&1 || { echo "ERROR: git not installed"; exit 1; }

# --- Directory layout --------------------------------------------------------
mkdir -p "${PROJECT_DIR}"
cd "${PROJECT_DIR}"

mkdir -p \
    src/footy_ev/{ingestion,db,db/migrations,models,backtest,risk,orchestration,utils,llm} \
    tests/{unit,integration,fixtures} \
    data/{raw,interim,processed,archive} \
    notebooks \
    scripts \
    configs \
    reports \
    .claude/{skills,agents} \
    .vscode

# Create __init__.py everywhere under src and tests
find src tests -type d -exec touch {}/__init__.py \;

# --- pyproject.toml ----------------------------------------------------------
cat > pyproject.toml <<'EOF'
[project]
name = "footy-ev"
version = "0.0.1"
description = "+EV sports betting pipeline for European football (free-tier edition)"
requires-python = ">=3.12"
dependencies = [
    # Data layer
    "duckdb>=1.1.0",
    "polars>=1.0.0",
    "pandas>=2.2.0",
    "pyarrow>=17.0.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    # Modeling
    "scikit-learn>=1.5.0",
    "scipy>=1.13.0",
    "statsmodels>=0.14.0",
    "xgboost>=2.1.0",
    "shap>=0.46.0",
    # Orchestration
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    # Scraping
    "playwright>=1.48.0",
    "httpx>=0.27.0",
    "beautifulsoup4>=4.12.0",
    "tenacity>=9.0.0",
    # Betting math (don't reinvent)
    "goto-conversion>=1.4.0",
    # LLM clients (local + free fallback)
    "ollama>=0.3.0",
    "google-generativeai>=0.8.0",
    # CLI / utils
    "typer>=0.12.0",
    "rich>=13.7.0",
    "loguru>=0.7.0",
    "python-dotenv>=1.0.0",
    "keyring>=25.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-cov>=5.0.0",
    "pytest-asyncio>=0.24.0",
    "hypothesis>=6.111.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "ipykernel>=6.29.0",
    "jupyter>=1.0.0",
    "pre-commit>=3.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "RET", "TCH"]
ignore = ["E501"]  # line length handled by formatter

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
no_implicit_optional = true
exclude = ["notebooks/", "build/", "dist/"]

[[tool.mypy.overrides]]
module = ["duckdb.*", "shap.*", "goto_conversion.*", "playwright.*", "ollama.*", "google.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration (require sample db)",
]
EOF

# --- .gitignore --------------------------------------------------------------
cat > .gitignore <<'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Environments
.venv/
.env
.env.*
!.env.example

# Data — never commit
data/
*.parquet
*.duckdb
*.duckdb.wal

# Jupyter
.ipynb_checkpoints/
*.ipynb_meta

# IDE
.idea/
*.swp
.DS_Store

# Build
build/
dist/

# Logs
*.log
logs/

# Secrets
secrets/
*.key
*.pem
EOF

# --- .claudeignore -----------------------------------------------------------
cat > .claudeignore <<'EOF'
data/
.venv/
__pycache__/
*.parquet
*.duckdb
*.duckdb.wal
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
*.log
secrets/
.env
.env.*
EOF

# --- .env.example ------------------------------------------------------------
cat > .env.example <<'EOF'
# Copy to .env and fill in. NEVER commit the .env file.

# --- Betfair (Phase 3+) ---
# Get a free Application Key (Delayed) from https://developer.betfair.com/
BETFAIR_APP_KEY=
BETFAIR_USERNAME=
BETFAIR_PASSWORD=
BETFAIR_CERT_PATH=

# --- Football-Data.org (Phase 0) ---
# Free tier: register at https://www.football-data.org/client/register
FOOTBALL_DATA_ORG_KEY=

# --- The Odds API (Phase 2+, optional) ---
# Free tier 500 req/month: https://the-odds-api.com/
THE_ODDS_API_KEY=

# --- Gemini API (free fallback for parsing tasks when Ollama too slow) ---
# Free key from https://aistudio.google.com/apikey
GEMINI_API_KEY=

# --- Runtime gates ---
LIVE_TRADING=false
LOG_LEVEL=INFO
DUCKDB_PATH=./data/footy_ev.duckdb

# --- LLM routing ---
# Which LLM to prefer for extraction tasks: ollama | gemini
LLM_EXTRACTOR=ollama
OLLAMA_MODEL=llama3.1:8b
GEMINI_MODEL=gemini-2.5-flash
EOF

# --- Makefile ----------------------------------------------------------------
cat > Makefile <<'EOF'
.PHONY: install test test-integration lint typecheck format precommit clean
.PHONY: ingest backtest paper-trade ollama-pull check-stack

install:
	uv sync --all-groups
	uv run playwright install chromium
	uv run pre-commit install
	@echo ""
	@echo "Install complete. Next: 'make check-stack' to verify everything is wired."

check-stack:
	@echo "Checking Python..."
	@uv run python --version
	@echo "Checking Ollama (optional)..."
	@command -v ollama >/dev/null && ollama --version || echo "  Ollama not installed (OK if using Gemini fallback)"
	@echo "Checking .env..."
	@test -f .env && echo "  .env exists" || echo "  .env missing — copy from .env.example"
	@echo "Smoke test..."
	@uv run pytest tests/unit -m "not slow" -q

ollama-pull:
	@command -v ollama >/dev/null || { echo "Install Ollama first: https://ollama.com/install"; exit 1; }
	ollama pull llama3.1:8b

test:
	uv run pytest tests/unit -m "not slow" -v

test-integration:
	uv run pytest tests/integration -v

test-all:
	uv run pytest -v

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src

precommit:
	uv run pre-commit run --all-files

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +

# --- Project-specific tasks --------------------------------------------------
ingest:
	uv run python -m footy_ev.ingestion.cli all

ingest-season:
	@if [ -z "$(SEASON)" ] || [ -z "$(LEAGUE)" ]; then \
		echo "Usage: make ingest-season SEASON=2024-2025 LEAGUE=EPL"; exit 1; \
	fi
	uv run python -m footy_ev.ingestion.cli season --season $(SEASON) --league $(LEAGUE)

backtest:
	@if [ -z "$(SEASON)" ] || [ -z "$(LEAGUE)" ]; then \
		echo "Usage: make backtest SEASON=2024-2025 LEAGUE=EPL"; exit 1; \
	fi
	uv run python -m footy_ev.backtest.cli --season $(SEASON) --league $(LEAGUE)

paper-trade:
	LIVE_TRADING=false uv run python -m footy_ev.orchestration.run
EOF

# --- pre-commit config -------------------------------------------------------
cat > .pre-commit-config.yaml <<'EOF'
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: check-merge-conflict
      - id: detect-private-key
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-requests]
        args: [--strict, --ignore-missing-imports]
EOF

# --- Claude Code settings ----------------------------------------------------
# Note: model is NOT hardcoded to opus. On Pro, defaulting to opus burns quota
# fast. Let the user pick per session via /model.
cat > .claude/settings.json <<'EOF'
{
  "permissions": {
    "auto_approve": [
      "Read",
      "Glob",
      "Grep",
      "Bash(make test*)",
      "Bash(make lint)",
      "Bash(make typecheck)",
      "Bash(make format)",
      "Bash(make check-stack)",
      "Bash(uv run pytest*)",
      "Bash(uv run python -c*)",
      "Bash(uv run ruff*)",
      "Bash(uv run mypy*)",
      "Bash(ls*)",
      "Bash(cat*)",
      "Bash(head*)",
      "Bash(tail*)",
      "Bash(git status)",
      "Bash(git diff*)",
      "Bash(git log*)"
    ],
    "deny": [
      "Bash(rm -rf*)",
      "Bash(git push --force*)",
      "Bash(git push -f*)",
      "Bash(curl*betfair*)",
      "Bash(*LIVE_TRADING=true*)",
      "Write(.env)",
      "Edit(.env)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "uv run ruff format \"$CLAUDE_FILE_PATH\" 2>/dev/null && uv run ruff check --fix \"$CLAUDE_FILE_PATH\" 2>/dev/null || true"
      }
    ]
  }
}
EOF

# --- VS Code workspace settings ---------------------------------------------
# Tuned to play well with both Claude Code and Copilot.
cat > .vscode/settings.json <<'EOF'
{
  "files.autoSave": "afterDelay",
  "files.autoSaveDelay": 1000,
  "files.watcherExclude": {
    "**/data/**": true,
    "**/.venv/**": true,
    "**/__pycache__/**": true,
    "**/.mypy_cache/**": true,
    "**/.ruff_cache/**": true,
    "**/.pytest_cache/**": true
  },
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.analysis.typeCheckingMode": "strict",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "github.copilot.enable": {
    "*": true,
    "markdown": false,
    "yaml": false,
    "plaintext": false
  },
  "github.copilot.editor.enableAutoCompletions": true
}
EOF

# --- Recommended extensions for this workspace ------------------------------
cat > .vscode/extensions.json <<'EOF'
{
  "recommendations": [
    "anthropic.claude-code",
    "github.copilot",
    "github.copilot-chat",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff",
    "tamasfe.even-better-toml",
    "redhat.vscode-yaml"
  ]
}
EOF

# --- Skills: starter set -----------------------------------------------------
mkdir -p .claude/skills/run-backtest
cat > .claude/skills/run-backtest/SKILL.md <<'EOF'
---
name: run-backtest
description: Run a walk-forward backtest for a given league and season range. Use when the operator asks to backtest, evaluate model performance, or compute CLV.
---

# Run a walk-forward backtest

When invoked, do the following:

1. Confirm the league code (EPL, LL, SA, BL, L1) and season range (e.g. 2018-2019 through 2024-2025).
2. Verify the data exists: `uv run python -c "from footy_ev.db import quick_check; quick_check('$LEAGUE', '$START_SEASON', '$END_SEASON')"`
3. If data is missing, STOP and tell the operator which seasons need ingestion. Do not silently proceed.
4. Run the backtest: `make backtest SEASON=$END_SEASON LEAGUE=$LEAGUE`
5. After completion, parse the report at `reports/backtest_$LEAGUE_$END_SEASON.json` and report:
   - Total bets placed
   - Mean CLV (%)
   - ROI (%)
   - Max drawdown
   - Reliability plot deviation (bins where |actual - predicted| > 2pp)
6. If reliability deviation is bad in any bin, recommend re-fitting the calibration layer.
7. If CLV is negative, do NOT recommend changes to thresholds. Negative CLV means the model has no edge; chasing thresholds is fitting to variance.

Never modify the backtest harness inline. If the harness has bugs, raise them as a separate task.
EOF

mkdir -p .claude/skills/ingest-season
cat > .claude/skills/ingest-season/SKILL.md <<'EOF'
---
name: ingest-season
description: Idempotently ingest one season of historical data for one league. Use when the operator says "ingest season X for league Y" or wants to backfill data.
---

# Ingest a single season for one league

When invoked:

1. Validate the season format: must be "YYYY-YYYY" with consecutive years.
2. Validate the league: must be one of EPL, LL, SA, BL, L1.
3. Run: `make ingest-season SEASON=$SEASON LEAGUE=$LEAGUE`
4. After completion, verify row counts:
   - football-data.co.uk match results: should be 380 (EPL/LL/SA), 306 (BL), 380 (L1)
   - If row count is materially off, STOP and report. Do not retry blindly.
5. Run the freshness audit: `uv run python -m footy_ev.ingestion.audit --season $SEASON --league $LEAGUE`
6. Report success with row counts per source.

Be polite to data sources: ≥2s between Understat requests, ≥3s between FBref requests.
Re-running this skill on a season that's already ingested must be a no-op (idempotency check via UPSERT or hash).
EOF

mkdir -p .claude/skills/audit-clv
cat > .claude/skills/audit-clv/SKILL.md <<'EOF'
---
name: audit-clv
description: Audit recent paper-trading or live-trading bets for closing line value. Use when the operator asks "how am I doing on CLV" or wants a CLV report.
---

# CLV audit

When invoked:

1. Default lookback is 30 days; accept an override.
2. Query the `bet_decisions` table for status='settled' AND placed_at >= NOW() - INTERVAL '30 days'.
3. Compute CLV per bet: `(odds_taken / closing_odds) - 1`.
4. Report:
   - Total settled bets
   - Mean CLV (%) and 95% CI via bootstrap (1000 resamples)
   - CLV by market type (1X2, OU2.5, BTTS, AH)
   - CLV by venue
   - Bets where odds_taken < closing_odds (negative CLV) — should be the minority
5. If mean CLV is negative AND the bootstrap lower bound is below 0, raise a flag: edge appears to be gone.
6. Output report to `reports/clv_audit_$DATE.md`.

Never silently exclude "outliers." If a bet looks anomalous, list it but include it.
EOF

mkdir -p .claude/skills/extract-with-llm
cat > .claude/skills/extract-with-llm/SKILL.md <<'EOF'
---
name: extract-with-llm
description: Extract structured data from unstructured text using local Ollama or Gemini API fallback. Use for parsing injury reports, lineup news, tactical changes from articles/tweets.
---

# Structured extraction from text

Routing logic:
1. Read `LLM_EXTRACTOR` from `.env`. Default: `ollama`.
2. If `ollama`: call local Llama 3.1 8B via `ollama` Python client.
3. If `gemini` or if Ollama is down: call Gemini 2.5 Flash via `google-generativeai` with `GEMINI_API_KEY`.

Discipline:
- ALWAYS pass a JSON schema (pydantic model) to the LLM.
- ALWAYS validate the response with the pydantic model. Reject invalid output, retry once, then log and skip.
- ALWAYS canonicalize entity names (player names, team names) against the `players` and `teams` tables in DuckDB. Fuzzy-match with rapidfuzz, threshold ≥85.
- NEVER let raw LLM output reach the model feature pipeline. It must pass through `events_ledger` first.

When the operator asks to "extract X from this text," confirm the target schema first, then proceed.
EOF

# --- Subagents: starter set --------------------------------------------------
cat > .claude/agents/data-scraper.md <<'EOF'
---
name: data-scraper
description: Isolated worker for long-running scraping tasks (Understat, FBref). Spawns its own context, returns only a summary.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
maxTurns: 50
---

You are a focused data-scraping subagent. You work in isolation from the main session.

Your responsibilities:
- Implement and run scrapers using Playwright (sync API, stealth mode, polite rate limiting >= 2s for Understat, >= 3s for FBref).
- Validate scraped data with pydantic models before writing to disk.
- Write to `data/raw/{source}/{league}/{season}/` as Parquet partitioned by date.
- Always include a `_metadata.json` next to each Parquet partition with: scraper version, scrape timestamp, row count, source URL.

You do not:
- Modify scraper code that already exists without explicit task instruction.
- Cache data anywhere except `data/raw/`.
- Bypass robots.txt or rate limits to "go faster."
- Use scrapers to bet-place; that is execution-layer concern.

When done, return a 5-bullet summary to the main session:
- Source scraped
- Date range covered
- Rows ingested
- Issues encountered (parsing errors, missing data, rate-limit hits)
- Suggested next action
EOF

cat > .claude/agents/backtest-runner.md <<'EOF'
---
name: backtest-runner
description: Isolated worker for long backtests. Use when running 5+ seasons of walk-forward backtest that would otherwise burn main-session context.
tools: Read, Bash, Glob, Grep
model: sonnet
maxTurns: 30
---

You are a focused backtest-runner subagent. You execute the backtest harness; you do not modify it.

Your responsibilities:
- Invoke `make backtest` with the parameters given.
- Stream progress (every N matches) so the main session can monitor.
- On completion, parse `reports/backtest_*.json` and produce a structured summary.

You do not:
- Modify model code, feature engineering, or calibration logic.
- Tune thresholds or hyperparameters.
- Cherry-pick or filter results.

Return summary in this exact structure (Markdown table) to main session:

| Metric | Value |
|---|---|
| League | ... |
| Season range | ... |
| Total bets | ... |
| Mean CLV (%) | ... |
| Mean ROI (%) | ... |
| Max drawdown (%) | ... |
| Sharpe (annualized) | ... |
| Calibration max bin error (pp) | ... |

Then list, separately, any anomalies you observed (e.g., one season with extreme variance).
EOF

# --- Minimum stub Python files so tests can run -----------------------------
cat > src/footy_ev/__init__.py <<'EOF'
"""footy-ev: +EV sports betting pipeline for European football."""

__version__ = "0.0.1"
EOF

cat > src/footy_ev/llm/__init__.py <<'EOF'
"""LLM extraction utilities. Routes between local Ollama and Gemini API fallback."""
EOF

cat > src/footy_ev/llm/router.py <<'EOF'
"""Router for LLM extraction tasks: prefer Ollama, fall back to Gemini."""

from __future__ import annotations

import os
from typing import Literal

LLMProvider = Literal["ollama", "gemini"]


def select_provider() -> LLMProvider:
    """Return the configured provider, defaulting to ollama."""
    val = os.getenv("LLM_EXTRACTOR", "ollama").lower()
    if val not in {"ollama", "gemini"}:
        raise ValueError(f"LLM_EXTRACTOR must be 'ollama' or 'gemini', got {val!r}")
    return val  # type: ignore[return-value]


if __name__ == "__main__":
    provider = select_provider()
    print(f"LLM extractor selected: {provider}")
EOF

cat > tests/unit/test_smoke.py <<'EOF'
"""Smoke test to verify the package imports."""

import footy_ev


def test_version() -> None:
    assert footy_ev.__version__ == "0.0.1"
EOF

cat > tests/unit/test_llm_router.py <<'EOF'
"""Test LLM provider selection."""

import os

import pytest

from footy_ev.llm.router import select_provider


def test_default_is_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_EXTRACTOR", raising=False)
    assert select_provider() == "ollama"


def test_gemini_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_EXTRACTOR", "gemini")
    assert select_provider() == "gemini"


def test_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_EXTRACTOR", "openai")
    with pytest.raises(ValueError, match="must be"):
        select_provider()
EOF

# --- README ------------------------------------------------------------------
cat > README.md <<'EOF'
# footy-ev

Local-first +EV sports betting pipeline for European football. Free-tier edition.

## Quick start

```bash
make install
make check-stack
```

## Stack

All free:
- Claude Pro for the IDE agent
- Gemini 2.5 Pro (student) as overflow + NotebookLM for paper review
- GitHub Pro (Student Pack) for repo + Copilot + Codespaces
- DuckDB + Parquet for storage
- Betfair Exchange Delayed API + football-data.co.uk + Understat + FBref for data
- Ollama (Llama 3.1 8B) for parsing, with Gemini API as fallback

See:
- `CLAUDE.md` — project conventions Claude Code follows automatically
- `BLUE_MAP.md` — architecture spec
- `PROJECT_INSTRUCTIONS.md` — full operator brief
- `SETUP_GUIDE.md` — step-by-step workflow
- `COSTS.md` — confirmation that this is all free

## Status

Phase 0: scaffold. No business logic yet.
EOF

# --- Init git & first commit -------------------------------------------------
git init -q
git add .
git commit -q -m "chore: bootstrap project scaffold (free-tier)" || true

# --- Final ------------------------------------------------------------------
echo ""
echo "==> Bootstrap complete in ${PROJECT_DIR}/"
echo ""
echo "Next steps:"
echo "  1. cd ${PROJECT_DIR}"
echo "  2. cp .env.example .env"
echo "     - Get a free Gemini API key: https://aistudio.google.com/apikey"
echo "     - Get a free Football-Data.org key: https://www.football-data.org/client/register"
echo "     - Betfair Application Key (Delayed) when you reach Phase 3: https://developer.betfair.com/"
echo "  3. Drop CLAUDE.md, PROJECT_INSTRUCTIONS.md, BLUE_MAP.md, SETUP_GUIDE.md, COSTS.md at the project root"
echo "  4. (Optional) Install Ollama: https://ollama.com/install"
echo "     Then: make ollama-pull"
echo "  5. make install"
echo "  6. make check-stack    # verifies everything is wired"
echo "  7. claude              # launch Claude Code"
echo "  8. /init               # let Claude inspect and propose CLAUDE.md additions (be selective on Pro!)"
echo ""
echo "Read SETUP_GUIDE.md for the detailed handoff workflow and rate-limit playbook."
