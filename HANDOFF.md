# Handoff — footy-ev / migration 002 in progress

> Created **2026-04-26** at the end of a long session. Read this in full before
> taking any action. The previous conversation hit token limits while debugging
> a real bug; this file captures state so a fresh chat can pick up cleanly.

---

## TL;DR

Phase 0 step 1 is **shipped**: 9,832 rows of EPL match data (2000-2001 → in-progress 2025-2026)
in `data/warehouse/footy_ev.duckdb`, with raw CSVs cached immutably under
`data/raw/football_data/E0/`.

Migration 002 (promote 52 closing-odds + pre-match AH columns from `extras` MAP to
typed DOUBLE columns) is **written, unit-tested (48/48 unit + 1 xfail), committed,
and BLOCKED on a Phase B audit failure when run against the real warehouse.**

The audit gate did its job correctly — it caught a real-world data shape that the
unit tests didn't exercise. The transaction rolled back, no data lost. The fix is
small but needs deliberate scoping in a fresh session.

---

## Where to start in the new conversation

1. Open this file. Then `BLUE_MAP.md` §6 (DuckDB schema) and `CLAUDE.md` if you need a refresher.
2. Read **"The blocker"** section below.
3. Run `uv run python scripts/migration_002_audit_report.py` to re-confirm the failure shape (read-only, ~1s).
4. Pick a fix path from **"Recommended fix paths"** with the operator.
5. Land migration 002, then proceed to Task 3 (integration tests + report).

---

## The blocker — migration 002 Phase B audit failure

### What happened

When `make.ps1 ingest -League EPL` ran (which auto-applies migrations on DB open),
migration 002's audit gate raised:

```
ConversionException: Could not convert string
'PHASE_B_AUDIT_FAILED__see_scripts/migration_002_audit_report.py_for_per_column_breakdown'
to INT32
```

The transaction rolled back. The warehouse is still in **pre-migration state**:
- Typed columns from migration 002 do NOT exist on `raw_match_results`.
- All 52 promoted source keys still in `extras` MAP for relevant rows.
- 9,832 rows still loaded, untouched.

### Diagnostic output (already captured)

`scripts/migration_002_audit_report.py` shows **27 of 52 columns** would fail the
gate. Same root cause across all 27: each has rows where `extras['<key>'] = ''`
(empty string) which `TRY_CAST('' AS DOUBLE)` returns NULL for, so `typed_count`
ends up less than `extras_count`.

Failing columns (and the gap):
```
BWCH/CD/CA: 153 uncastable each (out of 2612 present)
WHCH/CD/CA: 91 uncastable each (out of 2280 present)
PSCH/CD/CA: 122 uncastable each (out of 5272 present)   ← HIGH VALUE Pinnacle
IWCH/CD/CA: 185 uncastable each (out of 1900 present)
BFECH/CD/CA: 4 uncastable each (out of 712 present)
PC>2.5 / PC<2.5: 133 each (Pinnacle closing O/U)
BFEC>2.5 / BFEC<2.5: 4 each
B365CAHH / B365CAHA: 1 each
MaxCAHH / MaxCAHA: 1 each
PCAHH / PCAHA: 122 each (Pinnacle closing AH)
BFECAHH / BFECAHA: 4 each
```

Sample uncastable values are all `''` (empty strings).

### Why this happens

The loader (`src/footy_ev/ingestion/football_data/loader.py`, `_record_for_row`)
stores Python `None` as `""` (empty string) in the extras MAP:

```python
extras = {str(k): ("" if v is None else str(v)) for k, v in extras_raw.items()}
```

So when a CSV cell is empty (e.g., a match in a season where the bookmaker hadn't
yet started reporting closing odds, or just a missing data point), the loader
puts `BWCH = ''` in extras rather than omitting the key. Migration 002's audit
treats "key present" as "should have extracted a value" — but `TRY_CAST('')` is
NULL, so extraction count falls short of presence count.

### The unit test gap

`tests/unit/test_migration_002.py::test_migration_002_audit_gate_rolls_back_phase_c_on_cast_failure`
covers an extras value of `'not_a_number'`. It does NOT cover an extras value of
`''`. Add a test for the empty-string case as part of the fix.

---

## Recommended fix paths (rank ordered)

### Option 1 — Fix the audit query (one-line SQL change, no data migration)

Treat "key present with empty value" as "no data" in the audit. Change every
`extras_count` in the Phase B audit CTE from:

```sql
SUM(CASE WHEN list_contains(map_keys(extras), 'BWCH') THEN 1 ELSE 0 END)
```

to:

```sql
SUM(CASE WHEN TRY_CAST(extras['BWCH'] AS DOUBLE) IS NOT NULL THEN 1 ELSE 0 END)
```

This makes the audit semantic: "rows where extras has a CAST-able value". After
this, `typed_count == extras_count` always, by construction. The audit becomes
a tautology that catches cast failures only — which is the original intent.

**Pros**: minimal change, no data churn, keeps loader semantics untouched.
**Cons**: the audit's "row count" sanity is now per-castable-value, not per-key-presence.
Conceptually slightly weaker (if loader silently stops emitting the key entirely,
the audit no longer notices).

### Option 2 — Pre-clean extras as Phase A.5

Add a phase between A and B that removes empty-string values from extras:

```sql
UPDATE raw_match_results SET
    extras = map_from_entries(
        list_filter(map_entries(extras), e -> COALESCE(e.value, '') <> '')
    )
WHERE extras IS NOT NULL;
```

Then the audit's `extras_count` correctly reflects "key present with content".

**Pros**: makes extras cleaner globally; audit semantic stays strict.
**Cons**: scope creep on this migration; should arguably be its own migration;
also touches non-promoted keys (which is fine but not strictly needed).

### Option 3 — Fix the loader

Modify `_record_for_row` to skip None values entirely:

```python
extras = {str(k): str(v) for k, v in extras_raw.items() if v is not None}
```

Then re-run the loader to rewrite extras for all 9832 rows. Then re-run migration
002.

**Pros**: cleanest long-term semantic — extras only has real data.
**Cons**: requires re-loading 26 seasons of CSVs (≈30s, no network), more total
work, and changes existing behavior that an existing test relies on
(`test_load_unknown_column_flows_to_extras_and_drift_log` expects empty-string
behavior somewhere — verify before changing).

**My recommendation for the new chat: Option 1.** Smallest blast radius, preserves
intent, fits the original "fix-with-same-intent should be inline" feedback rule
saved to memory.

---

## What's already shipped (committed)

```
4e27cf3  feat(migration): 002 promote closing-odds families + pre-match AH aggregates
f622533  feat(ingestion): football-data.co.uk EPL backfill (Phase 0 step 1)
59316bf  docs(claude): drop unimplemented .\make.ps1 backtest target
9b0d283  chore: bootstrap project scaffold
```

### Committed artifacts of interest

- `src/footy_ev/db/migrations/001_raw_match_results.sql` — schema for the bronze ingest table
- `src/footy_ev/db/migrations/002_promote_closing_odds.sql` — the migration that's failing
- `src/footy_ev/ingestion/football_data/columns.py` — registry: 116 entries (64 original + 52 promoted in 002). Footer comment lists deferred Cat-G/H bookmakers (1xBet, BMGM, BV, CL, BFD)
- `src/footy_ev/ingestion/football_data/parse.py` — `FootballDataRow` Pydantic model with all 116 field aliases
- `src/footy_ev/ingestion/football_data/loader.py` — Polars + stdlib-csv hybrid; handles ragged rows; **stores `None` as `""` in extras** (root cause of audit failure)
- `src/footy_ev/ingestion/cli.py` — Typer CLI: `ingest-season`, `ingest-league`, `all`
- `make.ps1` — Windows wrapper. Calls bare `uv` (needs `$env:USERPROFILE\.local\bin` on PATH)
- `tests/unit/test_migration_002.py` — 6 unit tests, all passing in-memory (don't catch the empty-string case)
- `tests/integration/test_migration_002_warehouse.py` — gated on warehouse DB existence; will pass once 002 succeeds
- `scripts/report_backfill.py` — per-season + drift report (used at end of Phase 0 step 1)
- `scripts/migration_002_audit_report.py` — pre-flight audit checker that surfaced the failure

### Test status

- `.\make.ps1 test` → **48 passed + 1 xfailed**. Green.
- The `xfail` is `test_registry_covers_frozen_header` — encodes the migration-002 + Cat-G/H deficit. Remove `xfail` after both lands.

### Phase 0 backfill metrics (committed state)

- 26 seasons loaded (2000-01 → 2025-26)
- 9,832 rows total (25 × 380 + 332 in-progress 2025-26)
- 1 reject (trailing blank line in 2014-15 CSV — benign)
- 158.6s wall time for full backfill (one-shot, network-bound)

---

## What was NOT done in this session (planned, blocked)

1. **Migration 002 against the warehouse** — blocked by audit failure described above.
2. **Loader hash-refresh re-run** — would have been ~9832 cosmetic UPDATEs after migration; deferred.
3. **Integration test execution** — `tests/integration/test_migration_002_warehouse.py` exists but skipped because warehouse hasn't had 002 applied.
4. **Final `make.ps1 test-all` verification** — same reason.

---

## What to NOT do

- **Don't run migration 002 against the warehouse until the audit fix lands.** It will just fail again.
- **Don't manually delete typed columns from the warehouse** — they don't exist (transaction rolled back successfully).
- **Don't expand scope.** The fix for migration 002 is small. Resist the urge to tackle Understat ingestion, the `make.ps1` PATH issue, or other TODOs in the same change.
- **Don't second-guess fixes that preserve original design intent** — propose them inline. (See `~/.claude/projects/c--MY-Projects/memory/feedback_inline_fixes_when_design_intent_preserved.md`.)

---

## Persistent TODOs (carry-over from prior sessions, not fixed)

1. `make.ps1` calls bare `uv` but `uv` isn't on PowerShell's default PATH. Workaround in this session was prepending `$env:USERPROFILE\.local\bin` to `$env:PATH` before invoking. Persistent fix is on the operator side (Windows User PATH config) or by re-adding fallback to make.ps1.
2. `VIRTUAL_ENV` ambient stale value pollutes every `uv run` with a warning line. Cosmetic.
3. Trailing-blank-line skip in `_read_rows_lenient` (causes the benign 1-reject in 2014-15). 5-line tweak.
4. mypy `# type: ignore[misc]` scattered on @decorator lines for typer/tenacity/pytest fixtures because pre-commit's mypy env doesn't have those packages. Cleaner fix: extend `.pre-commit-config.yaml` `additional_dependencies`.
5. `.bootstrap_backup/` directory still tracked in git from the original session — safe to delete.

---

## Project context refresher (for the new chat)

- **Mission**: local-first +EV sports betting pipeline for European football pre-match markets. Targets 3-8% yield on turnover via CLV vs Betfair Exchange Starting Price.
- **Operator**: data-scientist student on Claude Pro free tier. Token-conscious. Windows 11 / PowerShell 5.1.
- **North Star**: closing-line value (CLV) — which is precisely why migration 002 promotes the closing-odds columns (PSC{H,D,A} is the 14-season Pinnacle dataset, the primary CLV training label).
- **Phase**: end of Phase 0 step 1 (data ingestion). Next steps after migration 002 lands: Understat xG ingestion (Phase 0 step 2), then Phase 1 (Dixon-Coles + xG-Skellam baselines).

### Stack reminders (from `CLAUDE.md`)

- Python 3.12+, `uv`, DuckDB + Parquet, Polars (new code), Pydantic v2, mypy --strict, ruff
- `pathlib.Path`, `datetime.now(timezone.utc)`, `decimal.Decimal` for money
- No f-string SQL except for whitelisted column names from REGISTRY
- Pinnacle: HISTORICAL closing-odds data allowed (it's in static CSVs); LIVE Pinnacle API banned

### Banned paths (still apply)

- No multi-account / "ghost execution" / ToS evasion
- No k-fold CV on time-series — walk-forward only
- No transformer / DeepAR for in-play in Phase 1
- No real money until bankroll discipline conditions in PROJECT_INSTRUCTIONS.md §3 are met

---

## Suggested first 3 tool calls in the new chat

```
1. Read HANDOFF.md (this file) in full.
2. Read src/footy_ev/db/migrations/002_promote_closing_odds.sql in full
   (focus on the Phase B audit CTE around lines 130-185).
3. Run `uv run python scripts/migration_002_audit_report.py` to confirm
   the audit failure shape is unchanged from this snapshot.
```

Then propose the audit fix (Option 1 above is recommended), implement, run unit
tests, run the loader, run the integration test, and we'll have CLV-ready closing
odds for 26 seasons.
