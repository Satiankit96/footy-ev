# Handoff — end of Phase 0 step 2 (Understat ingestion complete)

> Created **2026-05-01** at the close of TASK 3 (Understat loader + CLI + view + bootstrap aliases). Read this in full before doing anything else, then `LEARNING_LOG.md` (when it exists), then dive into the codebase. The previous `HANDOFF.md` (TASK 1 era — migration 002 audit blocker) is preserved at `HANDOFF.md.archive-2026-04-26` for historical reference.

---

## 1. Status banner

We are at the **end of Phase 0 step 2** of the project plan in `PROJECT_INSTRUCTIONS.md` §10. Phase 0 step 1 (football-data.co.uk historical match data + closing-odds promotions) is shipped. Phase 0 step 2 (Understat per-match xG ingestion) is shipped, including a temporal-aware entity-resolution layer (`team_aliases` + `v_understat_matches` view). The warehouse holds **9,832** football-data rows + **4,560** Understat rows for EPL across 2000-01 → 2025-26 (football-data) and 2014-15 → 2025-26 (Understat). Test suite is **71 passed / 2 skipped (network-gated) / 1 xfailed (Cat-G/H bookmakers, expected)**. Zero unmapped raw team names in `v_understat_matches`. The TASK 3 chunk is uncommitted — your immediate next action is to review the diff and commit the chunk.

After commit, the open architectural decision is whether to **(a)** extend ingestion to the other four target leagues (La Liga, Serie A, Bundesliga, Ligue 1) before starting Phase 1, or **(b)** start Phase 1 (Dixon-Coles + xG-Skellam baselines) on EPL-only and add the other leagues in parallel later. See §4 for the trade-off.

---

## 2. What's in the warehouse right now

`data/warehouse/footy_ev.duckdb` (DuckDB, mutable write surface — see invariant 6 below).

| Table / View | Rows | Coverage | Notes |
|---|---|---|---|
| `raw_match_results` | 9,832 | EPL, 2000-01 → 2025-26 | Football-data.co.uk. 2025-26 is in-progress (≈332/380 played as of last football-data ingest; refresh re-runs are idempotent via `source_row_hash`). |
| `raw_understat_matches` | 4,560 | EPL, 2014-15 → 2025-26 | Understat AJAX `/getLeagueData/EPL/<year>`. 2025-26 is in-progress (339/380 played as of last understat ingest on 2026-04-30). |
| `team_aliases` | 70 | EPL, 35 distinct `team_id`s | 35 football_data + 35 understat rows. Bootstrapped via `scripts/seed_team_aliases.sql`. NOT auto-applied — operator-run only. |
| `v_understat_matches` | 4,560 (parity) | matches base table 1:1 | Live view; 0 rows with NULL team_id. Re-applied by `apply_views()` on every `_open_db` call. |
| `schema_drift_log` | (only football-data drift, mostly resolved by migration 002) | — | Zero rows for `source='understat'` — Understat's payload shape is stable. The remaining football-data drift is the Cat-G/H bookmaker columns deferred for a future migration 004. |
| `teams` | 0 | — | Empty placeholder. `team_aliases.team_id` is the de-facto canonical for now. Populating `teams` is a Phase 1 prereq when we need attack/defense parameters per team. |

Migrations applied (lexically): `001_raw_match_results.sql`, `002_promote_closing_odds.sql`, `003_raw_understat_matches.sql`. Views applied (lexically): `v_understat_matches.sql`.

Raw cache on disk: `data/raw/football_data/E0/<season_code>.csv` and `data/raw/understat/EPL/<season>.json` + `.sha256` sidecar. Raw files are immutable per CLAUDE.md.

---

## 3. Architectural invariants

These are load-bearing — break them and the project fails in subtle ways. **`LEARNING_LOG.md` does not yet exist**; the operator plans to migrate this list (and the recent-decisions log in §6) into it. Until then, this file is the canonical record.

1. **CLV vs Betfair SP is the North Star metric.** Raw P&L is secondary. Any backtest report missing CLV is incomplete. (PROJECT_INSTRUCTIONS §6, BLUE_MAP §1.1)
2. **Walk-forward only on time-series.** K-fold CV is banned. (CLAUDE.md, BLUE_MAP §1.5, §7)
3. **Point-in-time correctness is mandatory.** Every feature view must accept `:as_of` and filter all source tables on `event_timestamp < :as_of`. No backdated news/lineups. (BLUE_MAP §6.1, §8)
4. **Append-only ledgers** for odds and events. No updates, no deletes on historical match rows except via the upsert-with-hash pattern (which preserves `inserted_at` history through the `source_row_hash` short-circuit).
5. **Raw downloaded data is immutable.** `data/raw/` is the source-of-truth archive. Never modify a cached file in place; if the upstream changes, capture a new file. (CLAUDE.md "File discipline")
6. **DuckDB tables are the mutable write surface; Parquet archive nightly; unified `v_*` views join both.** Downstream code queries `v_*` views and is agnostic to which side data came from. (Migration 001 header)
7. **Migrations are append-only and idempotent.** Every migration uses `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` / `ALTER TABLE ADD COLUMN IF NOT EXISTS`. No version-tracking ledger yet — add one when we have a migration that can't be expressed idempotently. (`src/footy_ev/db/__init__.py`)
8. **Entity resolution happens at QUERY time, not ingest time.** Loaders write raw `home_team_raw` / `away_team_raw` strings verbatim. The `team_aliases` table maps `(source, raw_name)` → `team_id`, with optional temporal bounds. Views (e.g., `v_understat_matches`) do the join. Fuzzy matching at ingest is banned — it would poison the canonical `teams` table. (Task 3 design)
9. **Pinnacle: historical closing-odds OK, live API banned.** PSC{H,D,A} is the 14-season Pinnacle CLV training label and is allowed because it's static CSV data. The live Pinnacle API (shut down July 2025) is permanently banned. (CLAUDE.md, migration 002 header)
10. **Real-money trading is gated on `LIVE_TRADING=true` AND the §3 PROJECT_INSTRUCTIONS bankroll discipline conditions.** Default behavior is paper-only. Soft-book limiting awareness is a design constraint, not an afterthought — execution router must degrade gracefully when a venue starts limiting. (PROJECT_INSTRUCTIONS §3, BLUE_MAP §1.2, §5)

Adjacent invariants reinforced by recent work (more flexible — these are codified in code review patterns rather than hard rules):

11. **Pydantic v2 `extra="allow"` + `extras` MAP column + `schema_drift_log`** is the canonical drift-handling pattern for any new ingestion source. Unknown source fields survive verbatim; `loader.py` logs them; operator periodically reviews and either promotes (migration) or marks resolved. Mirrors football_data and understat exactly.
12. **`source_row_hash` short-circuit for idempotent upserts.** sha256 over canonical-encoded parsed dict (including extras). On re-load, hash equality skips the upsert. The football_data loader's `total = inserted + updated + unchanged + rejected` accounting invariant is the canary; same applies to the understat loader.
13. **Typed-variant Pydantic fields are tripwires, not cosmetic.** `StrictBool` on `is_result` rejects coerced strings → loud failure on upstream encoding drift. `NaiveDatetime` / `AwareDatetime` pin the TZ contract at the model boundary. Use them deliberately when the contract matters.

---

## 4. What's next, ordered

### Immediate: commit the TASK 3 chunk

Suggested message skeleton (operator writes the actual commit message):

```
feat(understat): ingest per-match xG via AJAX endpoint, with team-alias view

  - migration 003: raw_understat_matches + team_aliases (temporal columns
    for future-proofing rebrands; bootstrap rows leave bounds NULL)
  - source.py: AJAX getLeagueData endpoint with X-Requested-With header
    (HTML inline-JSON deprecated by Understat Dec 2025; AJAX confirmed
    via understatapi v0.7.1 source — see commit 2025-12-17 there)
  - parse.py: Pydantic model with StrictBool + NaiveDatetime/AwareDatetime
    typed variants; convert_kickoff via stdlib zoneinfo (no pytz dep)
  - loader.py: ON CONFLICT upsert by understat_match_id, source_row_hash
    short-circuit, schema_drift_log on extras
  - CLI: ingest-understat-{season,league}, understat-detect-unmapped
  - bootstrap seed: 70 alias rows covering EPL 2014-15 → 2025-26 (35
    teams × 2 sources)
  - view: v_understat_matches with temporal alias join
  - tests: +18 unit (parse 11 + loader 6 + db_migrations 1) + 1 gated
    integration; 71 passed total
```

Commit covers `src/footy_ev/db/migrations/003_*`, `src/footy_ev/db/views/v_understat_matches.sql`, `src/footy_ev/db/__init__.py`, `src/footy_ev/ingestion/understat/`, `src/footy_ev/ingestion/cli.py`, `make.ps1`, `scripts/seed_team_aliases.sql`, `tests/fixtures/understat/`, `tests/unit/test_understat_*.py`, `tests/unit/test_db_migrations.py`, `tests/integration/test_understat_real.py`, this `HANDOFF.md`, archived `HANDOFF.md.archive-2026-04-26`.

### Short-term: Phase 0 closeout decision

**Option A — Multi-league ingestion before Phase 1.** Extend football_data + understat to La Liga, Serie A, Bundesliga, Ligue 1. Adds ~4× ingest time, ~60-80 more rows in `team_aliases`, and four more frozen-fixture seasons. Ingestion code is league-agnostic; only the `LEAGUE_TO_SOURCE_CODE` / `LEAGUE_TO_UNDERSTAT_CODE` maps need extending. Frozen-fixture tests for the parser would need one per league (defensible against future per-league source-shape drift).

**Option B — Start Phase 1 on EPL-only.** Ship Dixon-Coles 1X2 + xG-Skellam goals-totals + walk-forward backtest + isotonic calibration on a single league first. Single-league sample is ~9,800 matches (CLV-trainable) and is sufficient for the baseline. Add other leagues in parallel once the scaffolding is in place — Phase 1 model code should be league-parameterized from day one anyway.

**Recommendation: Option B.** Phase 1's open questions (CLV measurement plumbing, walk-forward backtest harness, isotonic calibration on edge-positive splits) all surface faster on EPL-only. A single league is enough sample. Multi-league adds breadth, not depth, and the modeling code wins more from validating-the-loop than from training-on-more-data. Add La Liga next, then prioritize the rest by liquidity (Bundesliga > Serie A > Ligue 1 on Betfair Exchange volume).

### Medium-term: Phase 1 (weeks 4–7 per PROJECT_INSTRUCTIONS §10)

- Dixon-Coles 1X2 baseline (BLUE_MAP §7).
- xG-Skellam goals-totals (BLUE_MAP §7).
- Walk-forward backtest harness with per-bet CLV computation (BLUE_MAP §7.1, §8).
- Isotonic calibration on holdout edges (BLUE_MAP §7).
- Target: positive CLV vs Betfair SP on a 1000+ bet sample. (PROJECT_INSTRUCTIONS §10 Phase 1 success criterion.)

This is where `teams` finally needs to be populated — Dixon-Coles needs per-team attack/defense parameters and we need a stable canonical key to attach them to. The `team_aliases.team_id` strings (`man_united`, `arsenal`, etc.) become the canonical `teams.team_id`.

### Long-term

- Phase 2: XGBoost ensemble + Kelly sizing (PROJECT_INSTRUCTIONS §10).
- Phase 3: LangGraph orchestration + Betfair Delayed key + paper-trading loop (PROJECT_INSTRUCTIONS §10).
- Phase 4: Real-money deployment, gated on bankroll discipline conditions in PROJECT_INSTRUCTIONS §3 (PROJECT_INSTRUCTIONS §10).

---

## 5. Outstanding TODOs / known debt

### Operator-side (no code change in this repo can fix)
- **Persistent Windows PATH for `uv`.** Sessions need `$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"` prepended before `make.ps1` invocations. Persistent fix is a Windows User PATH config or a re-added fallback in `make.ps1`.
- **Ambient `VIRTUAL_ENV` from a parent shell** pollutes every `uv run` with a "does not match the project environment path" warning. Cosmetic — outputs are correct.

### Code-side
- **`.bootstrap_backup/` still tracked in git** from the original session. Safe to delete.
- **No unit test for `_do_ingest_league` / `_do_ingest_understat_league` loop behavior.** The CLI's per-season loop with politeness sleep + 404 skip + idempotent re-load is not exercised by the unit suite. Test would mock `fetch_*` and assert correct loop control. Low priority.
- **`teams` table empty.** `team_aliases.team_id` is the de-facto canonical until Phase 1 demands a properly-populated `teams` row per club (with `country`, `aliases` array, etc.). Land a small bootstrap seed (`scripts/seed_teams.sql`) when Phase 1 starts.
- **Trailing-blank-line skip in `_read_rows_lenient`** causes the benign 1-reject in the 2014-15 football-data CSV. ~5-line cleanup.
- **mypy `# type: ignore[misc]` scattered on `@decorator` lines** for typer/tenacity/pytest fixtures because pre-commit's mypy env doesn't have those packages. Cleaner fix: extend `.pre-commit-config.yaml` `additional_dependencies`.
- **`tests/unit/test_football_data_frozen_header.py::test_registry_covers_frozen_header` xfail.** Encodes the deferred Cat-G/H bookmaker (1xBet, BMGM, BV, CL, BFD) deficit. Will need updating when those land in a future migration 004.
- **Cat-G/H bookmakers**: revisit migration 004 once 2026-27 starts and these columns persist into a second season. Currently they appear only in 2024-25 (one season's worth). Wait one more season before promoting; otherwise risk promoting columns that disappear again.
- **`addendum.md` at project root** contains an "Operator Vision Addendum" that hasn't been integrated into BLUE_MAP / PROJECT_INSTRUCTIONS. Operator's call whether to merge or leave as a separate file.

### Documentation
- **`LEARNING_LOG.md` does not yet exist.** Operator plans to create it; sections 3 and 6 of this handoff are interim canon until then. References to "Episode N" in code comments (notably `parse.py`'s `forecast_*_pct` field group docstring referencing Episode 11) point to entries that will live in `LEARNING_LOG.md` once written.

---

## 6. Recent decisions log (since last handoff)

Brief 2–3 line summary of each non-trivial decision since the prior handoff (2026-04-26 archived). Episode numbers are aspirational — they map to entries in the planned `LEARNING_LOG.md`.

**Episode 4 — Migration 002 empty-string fix (2026-04-26).** Phase B audit gate falsely flagged 27 columns because `extras['KEY']=''` (loader's representation of empty CSV cells) was counted by `list_contains(map_keys(extras), 'KEY')`. Fixed by changing the audit's `extras_count` to `extras[KEY] IS NOT NULL AND extras[KEY] <> ''`. Empty strings now treated as no-data; genuine cast failures (e.g., `'not_a_number'`) still fire the gate. Inline fix per saved-memory rule on preserving original design intent. Commit `3a46a55`.

**Episode 5 — Closing-odds coverage diagnostic (2026-04-26).** One-shot notebook (`notebooks/001_closing_odds_coverage.py`) confirmed PSCH coverage starts 2012-13, B365CH starts 2019-20, and post-coverage gaps are confined to the in-progress 2025-26 season (matches not yet played). matplotlib not in deps; plot block is guarded.

**Episode 6 — Plan-mode guard rails for new ingestion source (2026-04-26).** Pre-implementation plan for Understat got two-stage critique (Stage 1: confirm wire shape; Stage 2: read upstream library source). Stage 1 confirmed that Understat's `/league/<L>/<YYYY>` page no longer embeds inline JSON — the original plan's regex assumption was structurally invalid. Stop-and-report rule activated; saved hours of failed regex hacking.

**Episode 7 — `team_aliases` temporal columns (2026-04-26).** Added `active_from` / `active_to` to `team_aliases` to future-proof against mid-history rebrands. Bootstrap rows leave both NULL (interpreted as "valid forever"). PK stays `(source, raw_name)` — same-raw-name-reused-across-eras is unsupported by design; mid-history rebrands typically produce a NEW raw_name.

**Episode 8 — `kickoff_local` + `kickoff_utc` dual storage (2026-04-26).** Understat publishes naive league-local datetimes (`"2024-08-11 19:00:00"`, no offset). Stored both `kickoff_local` (audit/debug only) and `kickoff_utc` (canonical for downstream queries). TZ conversion via stdlib `zoneinfo` (no `pytz` dep). `LEAGUE_TZ = {"EPL": "Europe/London"}`; other leagues land when ingest extends.

**Episode 9 — Understat inline-JSON deprecated (Stage 1 finding, 2026-04-26).** Captured `EPL_2023.html` and `EPL_2025.html` from the team-page URL pattern as a fallback. Both are 18,791-byte JS-rendered shells with zero match-level data — confirmed BOTH `/league/<L>/<YYYY>` AND `/team/<T>/<YYYY>` no longer embed `datesData` blobs. Old plan's Option B (team pages) was dead.

**Episode 10 — Understat AJAX endpoint discovered (Stage 2 finding, 2026-04-26).** Read `understatapi` v0.7.1 source on GitHub. Commit message `Fix: use AJAX endpoints instead of HTML parsing` (2025-12-17) confirmed the timeline of Understat's site change. Endpoint: `GET https://understat.com/getLeagueData/<LEAGUE>/<YEAR>` with required header `X-Requested-With: XMLHttpRequest`. No auth, no cookies. Returns clean JSON with `dates` / `teams` / `players` keys. We now hit this directly with httpx; understatapi as a dep is unnecessary.

**Episode 11 — Forecast field is post-match attribution = pre-match leakage hazard (SUB-TASK 2a finding, 2026-04-26).** Empirical observation from the EPL_2025 fixture: `forecast.{w,d,l}` is populated on every played match (380/380 in 2023-24) but absent on all unplayed matches (0/42 in in-progress 2025-26). Implies it is a post-match attribution (computed from realized xG), not a pre-match prediction. **Using it as a pre-match feature is data leakage.** Stored for completeness via `forecast_*_pct` fields with explicit warning docstring on the field group in `parse.py`. (Operator plans to write the formal Episode 11 entry in `LEARNING_LOG.md`; the docstring already references it.)

**Episode 12 (proposed) — Temporal-alias-join test wording divergence (TASK 3 closeout, 2026-05-01).** The Task 3 spec described "two alias rows for the SAME raw_name with non-overlapping `active_from`/`active_to`". Migration 003's PK `(source, raw_name)` makes this literal scenario impossible — a Task 1 design decision the operator approved at the time. The test in `tests/unit/test_understat_loader.py::test_understat_loader_temporal_alias_join` was implemented for the realistic schema-compatible variant: TWO alias rows with DIFFERENT raw_names mapping to the SAME `team_id`, with disjoint validity windows (the canonical mid-history rebrand case). Test asserts in-window resolves, out-of-window yields NULL `team_id`. Same intent, schema-compatible setup; documented in the test docstring. **Operator's call whether to formalize as Episode 12 in `LEARNING_LOG.md`.**

---

## 7. How to resume

1. **Read in this order** (small to large): `CLAUDE.md` (always-on context, ≤200 lines), this `HANDOFF.md`, then `LEARNING_LOG.md` once it exists. Skip `BLUE_MAP.md` / `PROJECT_INSTRUCTIONS.md` unless the task references them directly — they're large.

2. **Confirm warehouse state** with three sanity queries (paste into a notebook or `uv run python -c "..."`):

   ```sql
   SELECT COUNT(*) FROM raw_match_results;       -- expect 9832
   SELECT COUNT(*) FROM raw_understat_matches;   -- expect 4560
   SELECT COUNT(*) FROM team_aliases;            -- expect 70
   ```

3. **Confirm test suite is green**:
   ```powershell
   $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
   .\make.ps1 test-all
   # expect: 71 passed, 2 skipped, 1 xfailed
   ```

4. **Pick the next-step path** (per §4):
   - If multi-league extension: extend `LEAGUE_TO_SOURCE` and `LEAGUE_TO_UNDERSTAT_CODE` maps, capture frozen fixtures per league, run ingests with politeness sleeps. ~half-day work per league.
   - If Phase 1 baseline: start with `src/footy_ev/models/dixon_coles.py` and a walk-forward harness in `src/footy_ev/eval/walk_forward.py`. Reference BLUE_MAP §7. Begin by populating `teams` from `team_aliases` distinct `team_id`s.

5. **Note environment quirks** (operator-side, not code-fixable):
   - `VIRTUAL_ENV` warning is cosmetic; ignore.
   - `uv` may not be on PowerShell's default PATH; prepend `$env:USERPROFILE\.local\bin` first.

---

## 8. What NOT to do

Abbreviated banned-paths reminder (full detail in `PROJECT_INSTRUCTIONS.md` §5 and `CLAUDE.md` "Banned paths"):

- **No multi-account / "ghost execution" / human-mimicking bet sequencers.** Route volume through Betfair Exchange.
- **No k-fold CV on time-series data.** Walk-forward only.
- **No Pinnacle as a live odds API source.** Public access shut down July 2025. Historical CSV closing-odds data IS allowed (it's in static football-data files).
- **No Transformer / DeepAR / RNN architectures for in-play in Phase 1.**
- **No local 4–8B LLMs as the "Analyst" producing probability estimates.** They parse text; they do not predict.
- **No paid services as if they're necessary.** The system must work end-to-end on free tooling.
- **No real-money bet placement until the bankroll discipline conditions in `PROJECT_INSTRUCTIONS.md` §3 are met.** Default `LIVE_TRADING=false`.
- **No mocking the database in integration tests.** Use a real (in-memory or temp-file) DuckDB.
- **No fuzzy entity resolution at ingest time.** Raw names go in verbatim; resolution happens at query time via `team_aliases`.
- **No f-string SQL with user/source-derived values.** Whitelisted column names from a registry are OK; everything else must be parameterized.
- **No business logic in notebooks.** Notebooks are exploration; reusable code moves to `src/footy_ev/`.
- **Don't trust `forecast_*_pct` as a pre-match feature.** It is post-match attribution. See Episode 11 in §6.

If a request seems to violate any of these, push back and cite this file or the upstream source.
