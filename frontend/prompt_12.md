# Frontend Stage 12 — Live Trading Gate Page

> Progress: 11 of 15 stages complete (~73%). Starting Stage 12 of 15.

## Mission

Build the live-trading gate page: prominent disabled banner, per-condition checklist validated against the warehouse, and absolutely no way to enable live trading through the UI. Small stage — 2 backend endpoints, 1 frontend page.

## Read first

1. `CLAUDE.md` — especially the `LIVE_TRADING` gating rules
2. `PROJECT_INSTRUCTIONS.md` §3 (Bankroll Discipline — the two conditions that must both be met)
3. `frontend/PLAN.md`:
   - §3 rule 1 (UI never bypasses LIVE_TRADING gating)
   - §7.14 (Live trading API — 2 endpoints + what's intentionally absent)
   - §8.13 (`/live-trading` page UX)
   - §12 Stage 12 acceptance criteria

## Deliverables

### A. Backend — Live trading router

Per §7.14:
- `GET /api/v1/live-trading/status` — returns `{enabled: false, gate_reasons: [list of unmet conditions]}`. Reads `LIVE_TRADING` env var. If somehow set to `true`, still returns `enabled: false` from this endpoint (the backend should refuse to acknowledge live mode through the UI — per §3 rule 1).
- `POST /api/v1/live-trading/check-conditions` — runs PROJECT_INSTRUCTIONS §3 checks against the warehouse:
  1. **Positive CLV on 1000+ bets over 60+ days** — query `bet_decisions` for settled bets with CLV, count them, compute mean CLV, compute date range. Returns: `{met: bool, bet_count: int, days_span: int, mean_clv_pct: float}`
  2. **Operator has confirmed disposable bankroll** — checks for a `BANKROLL_DISCIPLINE_CONFIRMED` env var (or similar flag). Returns: `{met: bool, flag_name: str, flag_set: bool}`
  - Returns each condition with pass/fail + observed values. **Read-only — zero writes.**

**There is intentionally NO endpoint to enable live trading.** If any request attempts to set `LIVE_TRADING` via the API (POST/PUT to any settings or env endpoint), return 405 Method Not Allowed.

**Checkpoint A:**
- Endpoints implemented
- Confirm status always returns `enabled: false` regardless of env state
- Confirm check-conditions is read-only (zero writes)
- Confirm no enable endpoint exists
- Backend test count delta

### B. Frontend — `/live-trading` page

Per §8.13:
- **Big red banner** at top: "LIVE TRADING IS DISABLED" — use `destructive` color, prominent, impossible to miss
- **Per-condition checklist** from the `check-conditions` response:
  - Each condition: icon (✓ green / ✗ red), description, observed value, required threshold
  - Example: "✗ Positive CLV on 1000+ bets over 60+ days — current: 47 bets, 12 days, CLV +0.8%"
  - Example: "✗ Operator has confirmed disposable bankroll — flag not set"
- **"Check conditions" button** — calls POST, updates the checklist, shows a toast with summary
- **Documentation panel** below the checklist: explains what each condition means and why both are required. Pull language from PROJECT_INSTRUCTIONS §3. Keep it concise — 2-3 sentences per condition.
- **NO enable button, no toggle, no switch, no form.** The page explains that enabling is done by editing `.env` after both conditions are independently validated.
- A note at the bottom: "To enable live trading, set `LIVE_TRADING=true` in `.env` after both conditions above are met. This cannot be done through the UI."

**Checkpoint B:**
- Banner styling (color token used)
- Confirm zero enable controls on the page
- Documentation panel content summary
- Frontend test count delta

## Known pre-existing issues (do NOT fix)

- 2 pre-existing pytest failures — ignore.

## Hard constraints

1. **No `git push`, no remote sync.** Local commits + `frontend-stage-12-complete` tag only.
2. **No edits to `src/footy_ev/`.** Read-only queries against the warehouse only.
3. **No new deps in main project `pyproject.toml`.**
4. **No scope creep into Stage 13 (Polish).**
5. **No enable endpoint. No toggle. No way to activate live trading from the UI. Period.**
6. **mypy --strict clean** backend. **tsc --noEmit clean** frontend.

## Required final report

1. **Checkpoints A–B** verbatim.
2. **Test counts:** backend before/after, frontend before/after. Confirm green.
3. **Files touched in `src/footy_ev/`** — should be zero.
4. **§12 Stage 12 acceptance check:**
   - [ ] Visiting the page shows red banner
   - [ ] Conditions are checked accurately against the warehouse data
   - [ ] The page has no enable button
   - [ ] Attempting to set LIVE_TRADING=true via the API returns 405
5. **Deviations from spec** — or "none."
6. **Any constraint violations or scope creep — explicit list, even if zero.**
7. **Brief summary of what you did** — 3–5 sentences. What shipped, what to expect in Stage 13.
