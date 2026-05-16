# Frontend Stage 13 — Polish, Command Palette, Settings

> Progress: 12 of 15 stages complete (~80%). Starting Stage 13 of 15.

## Mission

Polish pass across the entire app: cmd-k command palette, `/settings` page with server-side persistence, loading/empty/error states on every page, skeleton loaders, error boundaries, toast coverage. This stage has no new domain logic — it's UX quality.

## Read first

1. `frontend/PLAN.md`:
   - §7.15 (Settings API — 2 endpoints)
   - §8.14 (`/settings` page UX)
   - §9.4 (shadcn components — `Command` for cmd-k)
   - §9.5 (Layout — cmd-k trigger in topbar)
   - §12 Stage 13 acceptance criteria
2. Existing code:
   - `frontend/web/components/layout/topbar.tsx` — cmd-k trigger goes here
   - `frontend/web/app/` — every page route; audit each for loading/empty/error states
   - Sonner is already in deps (used for toasts since Stage 5)

## Deliverables

### A. Backend — Settings router

Per §7.15:
- `GET  /api/v1/settings` — returns operator settings (theme, density, default page sizes, default time range). Persisted server-side in a small JSON file or DuckDB table — pick whichever is simpler.
- `PUT  /api/v1/settings` — body: full settings object, atomic replace. Validated via Pydantic schema.

Settings schema (at minimum):
```
{
  theme: "dark" | "light" | "system",
  density: "comfortable" | "compact",
  default_page_size: 25 | 50 | 100,
  default_time_range_days: 7 | 14 | 30 | 90,
}
```

**Checkpoint A:**
- Endpoints implemented
- Persistence mechanism chosen (file vs DuckDB)
- Backend test count delta

### B. Frontend — `/settings` page

Per §8.14:
- Theme selector (dark/light/system) — wired to `next-themes`
- Density toggle (comfortable/compact) — applies globally via CSS class or Tailwind variant
- Default page size selector
- Default time range selector
- Credentials status section (read-only, from `/kalshi/credentials/status`) — green/red indicators
- Sign-out button → POST `/auth/logout` → redirect to `/login`
- Save button → PUT `/settings` → toast confirmation

Settings load on app init and are available globally (Zustand store or React context — pick one).

**Checkpoint B:**
- Settings persistence confirmed (survives page reload)
- Density toggle effect described
- Frontend test count delta

### C. Command palette (cmd-k)

Use shadcn `Command` component (or `cmdk` library if shadcn doesn't have it yet — check).

- Trigger: `Cmd+K` (Mac) / `Ctrl+K` (Windows) — also clickable from topbar
- Sections:
  - **Navigation:** all main routes (Dashboard, Pipeline, Kalshi, Aliases, Fixtures, Predictions, Bets, CLV, Risk, Warehouse, Diagnostics, Audit, Settings, Live Trading)
  - **Search Fixtures:** type fixture ID or team name → results from `/fixtures?` endpoint (debounced 300ms)
  - **Search Aliases:** type ticker → results from `/aliases?` endpoint
  - **Search Bets:** type decision ID → results from `/bets?` endpoint
  - **Actions:** "Run pipeline cycle", "Run bootstrap", "Check live trading conditions", "Backfill CLV"
- Arrow keys to navigate, Enter to select, Esc to close
- Recently used items float to the top (client-side, Zustand or localStorage)

**Checkpoint C:**
- Trigger key binding confirmed
- Search sections listed
- Action items listed
- Frontend test count delta

### D. Loading / empty / error states audit

Audit **every page** in the app. For each:
- **Loading:** skeleton loader or spinner while data fetches (use shadcn `Skeleton`)
- **Empty:** friendly message when no data exists (not a blank page). Examples: "No fixtures match your filters", "No paper bets yet — run a pipeline cycle to generate predictions", "No audit actions recorded yet"
- **Error:** error boundary catches render failures; shows a card with "Something went wrong" + "Try again" button + the `request_id` for debugging. No raw stack traces.

Also verify:
- Every mutating action shows a sonner toast on success AND on failure
- Failed API calls show toast with the error message from the API envelope (not a generic "Error")

List every page you audited and what you added/fixed in the final report.

**Checkpoint D:**
- Pages audited (full list)
- Skeleton loader component used
- Error boundary component file path
- Number of empty states added/improved
- Number of toast gaps filled

### E. Chart tooltip + table polish

- Chart tooltips: verify all recharts charts (SnapshotTimeline, CLV rolling, CLV histogram, bankroll sparkline, stakes histogram, exposure bars) have rich tooltips per §9.7
- Tables: verify all TanStack tables have proper empty states, column visibility toggles work, and pagination shows "Showing X–Y of Z"
- Monospace: verify tickers, IDs, hashes, odds all use monospace font per §9.2

**Checkpoint E:**
- Charts audited (list)
- Tables audited (list)
- Monospace audit result

## Known pre-existing issues (do NOT fix)

- 2 pre-existing pytest failures — ignore.

## Hard constraints

1. **No `git push`, no remote sync.** Local commits + `frontend-stage-13-complete` tag only.
2. **No edits to `src/footy_ev/`.**
3. **No new domain logic.** This stage is pure UX polish. No new data endpoints beyond settings.
4. **No scope creep into Stage 14 (Testing pass).**
5. **mypy --strict clean** backend. **tsc --noEmit clean** frontend.

## Required final report

1. **Checkpoints A–E** verbatim.
2. **Test counts:** backend before/after, frontend before/after. Confirm green.
3. **Files touched in `src/footy_ev/`** — should be zero.
4. **Full list of pages audited** for loading/empty/error states, with what was added per page.
5. **§12 Stage 13 acceptance check:**
   - [ ] cmd-k works across the app
   - [ ] Every page handles loading, empty, and error states gracefully
   - [ ] No raw error stacks shown to user; logged server-side
6. **Deviations from spec** — or "none."
7. **Any constraint violations or scope creep — explicit list, even if zero.**
8. **Brief summary of what you did** — 5–8 sentences. What shipped, what was tricky, what to expect in Stage 14.
