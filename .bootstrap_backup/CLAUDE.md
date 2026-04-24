# CLAUDE.md — footy-ev project

> Always-on context for Claude Code. Read at the start of every session.
> Keep this file under 200 lines; for full detail link out to `BLUE_MAP.md` and `PROJECT_INSTRUCTIONS.md`.

## What this project is

A local-first +EV sports betting pipeline targeting European football (EPL, La Liga, Serie A, Bundesliga, Ligue 1) pre-match markets. Goal: sustainable 3–8% yield on turnover, measured by closing-line value (CLV) against Betfair Exchange Starting Price.

Operator is a **student on Claude Pro (free tier)**. Token budget is finite. Be deliberate.

For full mission, banned paths, and rigor requirements, read `PROJECT_INSTRUCTIONS.md`.
For architecture, schema, and code skeletons, read `BLUE_MAP.md`.

## Operator profile

The operator is a Data Scientist / Software Engineer student. Skip introductory explanations of ML, Python, databases, or software architecture. Default to advanced-practitioner level.

## Token discipline (read this every session)

- Default model: `sonnet` (cheaper). Switch to `opus` only for planning multi-file changes or hard architectural calls.
- Prefer focused single-file changes over multi-file refactors.
- Never re-read a file you already have in context unless the file changed.
- If a task is large, propose a 3-step plan and ask which step to start with — don't try to do all 3 in one response.
- Don't pad responses with restatements of the question, sycophantic openers, or recaps of prior work.
- When uncertain, ask one targeted question rather than producing a long speculative answer.
- If the operator says "be brief," respond in ≤5 sentences.

## Stack (hard constraints, all free)

- **Python 3.12+** managed by `uv` (not poetry, not pip-tools, not pipenv)
- **DuckDB + Parquet** for analytical storage; never propose Postgres for analytical workload
- **LangGraph** for orchestration
- **scikit-learn, scipy, statsmodels, xgboost** for modeling
- **Polars** for new dataframe code; pandas allowed for legacy compat
- **Pydantic v2** for all data validation
- **Playwright** (sync API + stealth) for scraping
- **Ollama** (Llama 3.1 8B) for local LLM extraction; fall back to Gemini API free tier if RAM-constrained
- **Betfair Exchange API (Delayed key, free)** as primary odds source
- **Oracle Cloud Free Tier** or **DigitalOcean (Student credit)** for 24/7 deployment

## Banned paths

Do not propose, design, or implement any of the following. If asked, push back and explain why:

- Multi-account schemes, "ghost execution," human-mimicking bet sequencers, or any technique whose purpose is to evade sportsbook ToS. Route volume through exchanges instead.
- K-fold cross-validation on time-series data. Walk-forward only.
- Pinnacle as a live odds API source (public access shut down July 2025).
- Transformer / DeepAR / RNN architectures for in-play in Phase 1.
- Local 4–8B LLMs as the "Analyst" producing probability estimates. They parse text; they do not predict.
- Paid services as if they're necessary. The system must work end-to-end on free tooling.
- Real-money bet placement until the bankroll discipline conditions in `PROJECT_INSTRUCTIONS.md` §3 are met.

## Code conventions

- Type hints on every function signature. `mypy --strict` passes or it doesn't ship.
- Docstrings in Google style on every public function.
- Every module has a `if __name__ == "__main__":` smoke test that runs in <2 seconds.
- Imports sorted by `ruff` (isort-compatible). One import per line.
- Use `pathlib.Path` not `os.path`.
- Use `datetime.now(timezone.utc)` not `datetime.utcnow()`.
- Decimal money: use `decimal.Decimal`, never `float`, for stakes and P&L.
- Random seeds set explicitly in any model/sim code: `np.random.default_rng(seed)`.

## DuckDB conventions

- Schema lives in `src/footy_ev/db/schema.sql`. Never modify schema directly; write a migration in `src/footy_ev/db/migrations/`.
- All queries use parameterized statements. No f-string SQL ever.
- Feature views must accept an `:as_of` parameter and filter all source tables on `event_timestamp < :as_of`. Point-in-time correctness is non-negotiable.
- Use CTEs (`WITH ... AS`) over nested subqueries.

## Workflow rules

- **Plan before implementing** anything that touches more than one file. Use plan mode (`/model opus` then describe the change) — but switch back to sonnet for the actual implementation to save tokens.
- **Test discipline**: no new function ships without a test. No bug fix ships without a regression test.
- **CLV is the North Star metric**. Any backtest report that doesn't include CLV vs Betfair SP is incomplete.
- **Ask before doing destructive operations**: `git push --force`, dropping DuckDB tables, deleting from `data/`. These should be in the deny-list of `.claude/settings.json` regardless.
- **No business logic in notebooks**. Notebooks are for exploration. Anything reusable moves to `src/footy_ev/`.

## Test commands

- `make test` — fast unit tests (target: <30 seconds)
- `make test-integration` — slower integration tests with sample DuckDB
- `make lint` — ruff
- `make typecheck` — mypy --strict
- `make backtest SEASON=2024-2025 LEAGUE=EPL` — walk-forward backtest

## Bash commands

- Use `uv run <command>` for any Python execution; do not activate the venv manually.
- Use `uv add <pkg>` to add dependencies, not `pip install`.
- Long-running commands (scrapers, full-season backtests) go in `scripts/` and are launched via `make`.

## File discipline

- Real money / live trading is gated by `LIVE_TRADING=true` env var. Default behavior is paper-only.
- Secrets live in `.env` (gitignored, claudeignored). Never hard-code API keys.
- Raw downloaded data is immutable. Place in `data/raw/` and never modify in place.
- Be polite to free data sources: ≥2s between Understat requests, ≥3s between FBref requests. Use `tenacity` for retries with exponential backoff.

## Known failure modes to avoid

For each of these, see `BLUE_MAP.md` §1 for the full mitigation:

- **Edge already priced in** → measure CLV, not raw P&L
- **Account limiting** → exchange-first execution, no soft-book exposure scaling
- **Silent data pipeline breakage** → freshness checks + circuit breakers
- **LLM hallucination poisoning features** → pydantic validation + entity resolution
- **Overfitting disguised as feature engineering** → walk-forward + permutation importance
- **Bankroll ruin from noisy Kelly** → fractional Kelly + per-bet cap
- **Token budget ruin** → see "Token discipline" section above

## When in doubt

- If a request seems to violate the banned paths, push back. Cite this file.
- If a request seems too vague to plan from, ask one targeted clarifying question.
- If you've been working for a while and the context feels stale, suggest `/clear` and a fresh start with a focused prompt.
- If the operator hits a rate limit, suggest they continue in Gemini 2.5 Pro web chat for the same task and paste results back when Pro resets.
