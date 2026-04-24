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
