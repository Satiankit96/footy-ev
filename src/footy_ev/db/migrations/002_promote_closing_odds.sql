-- Migration 002: promote closing-odds families + pre-match AH aggregates from
-- the extras MAP into typed columns on raw_match_results.
--
-- HIGH VALUE: PSC{H,D,A} is the 14-season Pinnacle closing-odds dataset, our
-- primary CLV training label. Per CLAUDE.md exception: historical Pinnacle data
-- in static CSVs is allowed; live Pinnacle API access remains banned.
--
-- This migration is run inside a single transaction so that a Phase B audit
-- failure (between Phase B and Phase C) rolls back ALL changes — Phase C
-- destroys the source-of-truth keys in extras, so we never want to reach it
-- if Phase B's extraction didn't produce the row counts we expect.
--
-- Idempotent. Re-running is a no-op via:
--   - ADD COLUMN IF NOT EXISTS (DuckDB 0.10+)
--   - COALESCE(existing_typed, extras_value) keeps prior typed values intact
--     so a re-run after Phase C (extras scrubbed) is a no-op AND a re-run
--     before Phase C with stale extras still preserves loader-written data
--   - Phase C's list_filter + map_from_entries is set-based: filtering
--     already-removed keys is a no-op
--
-- Trusts loader invariant: each extras key appears at most once per row
-- (Python dict semantics + the test_loader_extras_keys_unique test).
-- DuckDB 1.5.x's ``MAP['key']`` returns the value directly (not a list),
-- so ``extras['SourceName']`` is the cell value.

BEGIN TRANSACTION;

-- ============================================================================
-- PHASE A — ALTER TABLE: add 52 typed columns
-- ============================================================================

-- 1X2 closing odds (9 books × 3 = 27)
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS b365ch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS b365cd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS b365ca DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bwch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bwcd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bwca DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS whch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS whcd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS whca DOUBLE;
-- HIGH VALUE: 14-season Pinnacle closing-odds dataset, primary CLV training label.
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS psch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS pscd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS psca DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS iwch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS iwcd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS iwca DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS vcch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS vccd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS vcca DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS maxch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS maxcd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS maxca DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avgch DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avgcd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avgca DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bfech DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bfecd DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bfeca DOUBLE;

-- O/U 2.5 closing (5 books × 2 = 10)
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS b365c_over_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS b365c_under_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS maxc_over_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS maxc_under_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avgc_over_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avgc_under_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS pc_over_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS pc_under_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bfec_over_25 DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bfec_under_25 DOUBLE;

-- AH closing line + per-book closing AH (1 + 5 × 2 = 11)
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS ahc_line DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS b365c_ah_home DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS b365c_ah_away DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS maxc_ah_home DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS maxc_ah_away DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avgc_ah_home DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avgc_ah_away DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS pc_ah_home DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS pc_ah_away DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bfec_ah_home DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS bfec_ah_away DOUBLE;

-- Pre-match AH aggregates (2 × 2 = 4)
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS max_ah_home DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS max_ah_away DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avg_ah_home DOUBLE;
ALTER TABLE raw_match_results ADD COLUMN IF NOT EXISTS avg_ah_away DOUBLE;

-- ============================================================================
-- PHASE B — Extract from extras MAP into typed columns
-- ----------------------------------------------------------------------------
-- COALESCE direction is COALESCE(existing_typed, extras_value) — the EXISTING
-- typed value WINS when set. On initial run, typed is NULL (Phase A just added
-- the column) so COALESCE falls through to the extras value. On any subsequent
-- run, the typed value already populated takes precedence over whatever happens
-- to be in extras. This means:
--   1. Initial: typed=NULL, extras='1.75' -> typed becomes 1.75 (extracted).
--   2. Re-run after Phase C: typed=1.75, extras has no key -> typed stays 1.75.
--   3. Re-run with stale extras (e.g., audit rolled back Phase C): typed=1.75,
--      extras='9.99' -> typed stays 1.75 (does NOT clobber loader-written data).
-- Loader is the long-term source of truth for typed values; this migration
-- only seeds them from extras on first run.
-- ============================================================================

UPDATE raw_match_results SET
    b365ch         = COALESCE(b365ch, TRY_CAST(extras['B365CH'] AS DOUBLE)),
    b365cd         = COALESCE(b365cd, TRY_CAST(extras['B365CD'] AS DOUBLE)),
    b365ca         = COALESCE(b365ca, TRY_CAST(extras['B365CA'] AS DOUBLE)),
    bwch           = COALESCE(bwch, TRY_CAST(extras['BWCH'] AS DOUBLE)),
    bwcd           = COALESCE(bwcd, TRY_CAST(extras['BWCD'] AS DOUBLE)),
    bwca           = COALESCE(bwca, TRY_CAST(extras['BWCA'] AS DOUBLE)),
    whch           = COALESCE(whch, TRY_CAST(extras['WHCH'] AS DOUBLE)),
    whcd           = COALESCE(whcd, TRY_CAST(extras['WHCD'] AS DOUBLE)),
    whca           = COALESCE(whca, TRY_CAST(extras['WHCA'] AS DOUBLE)),
    psch           = COALESCE(psch, TRY_CAST(extras['PSCH'] AS DOUBLE)),
    pscd           = COALESCE(pscd, TRY_CAST(extras['PSCD'] AS DOUBLE)),
    psca           = COALESCE(psca, TRY_CAST(extras['PSCA'] AS DOUBLE)),
    iwch           = COALESCE(iwch, TRY_CAST(extras['IWCH'] AS DOUBLE)),
    iwcd           = COALESCE(iwcd, TRY_CAST(extras['IWCD'] AS DOUBLE)),
    iwca           = COALESCE(iwca, TRY_CAST(extras['IWCA'] AS DOUBLE)),
    vcch           = COALESCE(vcch, TRY_CAST(extras['VCCH'] AS DOUBLE)),
    vccd           = COALESCE(vccd, TRY_CAST(extras['VCCD'] AS DOUBLE)),
    vcca           = COALESCE(vcca, TRY_CAST(extras['VCCA'] AS DOUBLE)),
    maxch          = COALESCE(maxch, TRY_CAST(extras['MaxCH'] AS DOUBLE)),
    maxcd          = COALESCE(maxcd, TRY_CAST(extras['MaxCD'] AS DOUBLE)),
    maxca          = COALESCE(maxca, TRY_CAST(extras['MaxCA'] AS DOUBLE)),
    avgch          = COALESCE(avgch, TRY_CAST(extras['AvgCH'] AS DOUBLE)),
    avgcd          = COALESCE(avgcd, TRY_CAST(extras['AvgCD'] AS DOUBLE)),
    avgca          = COALESCE(avgca, TRY_CAST(extras['AvgCA'] AS DOUBLE)),
    bfech          = COALESCE(bfech, TRY_CAST(extras['BFECH'] AS DOUBLE)),
    bfecd          = COALESCE(bfecd, TRY_CAST(extras['BFECD'] AS DOUBLE)),
    bfeca          = COALESCE(bfeca, TRY_CAST(extras['BFECA'] AS DOUBLE)),
    b365c_over_25  = COALESCE(b365c_over_25, TRY_CAST(extras['B365C>2.5'] AS DOUBLE)),
    b365c_under_25 = COALESCE(b365c_under_25, TRY_CAST(extras['B365C<2.5'] AS DOUBLE)),
    maxc_over_25   = COALESCE(maxc_over_25, TRY_CAST(extras['MaxC>2.5'] AS DOUBLE)),
    maxc_under_25  = COALESCE(maxc_under_25, TRY_CAST(extras['MaxC<2.5'] AS DOUBLE)),
    avgc_over_25   = COALESCE(avgc_over_25, TRY_CAST(extras['AvgC>2.5'] AS DOUBLE)),
    avgc_under_25  = COALESCE(avgc_under_25, TRY_CAST(extras['AvgC<2.5'] AS DOUBLE)),
    pc_over_25     = COALESCE(pc_over_25, TRY_CAST(extras['PC>2.5'] AS DOUBLE)),
    pc_under_25    = COALESCE(pc_under_25, TRY_CAST(extras['PC<2.5'] AS DOUBLE)),
    bfec_over_25   = COALESCE(bfec_over_25, TRY_CAST(extras['BFEC>2.5'] AS DOUBLE)),
    bfec_under_25  = COALESCE(bfec_under_25, TRY_CAST(extras['BFEC<2.5'] AS DOUBLE)),
    ahc_line       = COALESCE(ahc_line, TRY_CAST(extras['AHCh'] AS DOUBLE)),
    b365c_ah_home  = COALESCE(b365c_ah_home, TRY_CAST(extras['B365CAHH'] AS DOUBLE)),
    b365c_ah_away  = COALESCE(b365c_ah_away, TRY_CAST(extras['B365CAHA'] AS DOUBLE)),
    maxc_ah_home   = COALESCE(maxc_ah_home, TRY_CAST(extras['MaxCAHH'] AS DOUBLE)),
    maxc_ah_away   = COALESCE(maxc_ah_away, TRY_CAST(extras['MaxCAHA'] AS DOUBLE)),
    avgc_ah_home   = COALESCE(avgc_ah_home, TRY_CAST(extras['AvgCAHH'] AS DOUBLE)),
    avgc_ah_away   = COALESCE(avgc_ah_away, TRY_CAST(extras['AvgCAHA'] AS DOUBLE)),
    pc_ah_home     = COALESCE(pc_ah_home, TRY_CAST(extras['PCAHH'] AS DOUBLE)),
    pc_ah_away     = COALESCE(pc_ah_away, TRY_CAST(extras['PCAHA'] AS DOUBLE)),
    bfec_ah_home   = COALESCE(bfec_ah_home, TRY_CAST(extras['BFECAHH'] AS DOUBLE)),
    bfec_ah_away   = COALESCE(bfec_ah_away, TRY_CAST(extras['BFECAHA'] AS DOUBLE)),
    max_ah_home    = COALESCE(max_ah_home, TRY_CAST(extras['MaxAHH'] AS DOUBLE)),
    max_ah_away    = COALESCE(max_ah_away, TRY_CAST(extras['MaxAHA'] AS DOUBLE)),
    avg_ah_home    = COALESCE(avg_ah_home, TRY_CAST(extras['AvgAHH'] AS DOUBLE)),
    avg_ah_away    = COALESCE(avg_ah_away, TRY_CAST(extras['AvgAHA'] AS DOUBLE))
WHERE extras IS NOT NULL;

-- ============================================================================
-- PHASE B AUDIT — gate Phase C scrub
-- ----------------------------------------------------------------------------
-- Per-column invariant: rows_with_typed_value_post_phase_B must equal
-- rows_with_extras_key_post_phase_B (Phase B doesn't touch extras, so this
-- is also the pre-Phase-B count). If any column shows a mismatch, the SELECT
-- below tries to cast the literal 'PHASE_B_AUDIT_FAILED' to INTEGER, which
-- raises ConversionException. Because we're inside BEGIN TRANSACTION, the
-- error rolls back Phase A + Phase B, AND Phase C never runs. This protects
-- the source-of-truth keys in extras until the operator investigates.
-- A human-readable per-column report is produced by
-- scripts/migration_002_audit_report.py for eyeballing during initial run.
-- ============================================================================

WITH per_col AS (
    SELECT 'B365CH' AS col, SUM(CASE WHEN b365ch IS NOT NULL THEN 1 ELSE 0 END) AS typed_count, SUM(CASE WHEN (extras['B365CH'] IS NOT NULL AND extras['B365CH'] <> '') THEN 1 ELSE 0 END) AS extras_count FROM raw_match_results
    UNION ALL SELECT 'B365CD', SUM(CASE WHEN b365cd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['B365CD'] IS NOT NULL AND extras['B365CD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'B365CA', SUM(CASE WHEN b365ca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['B365CA'] IS NOT NULL AND extras['B365CA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BWCH', SUM(CASE WHEN bwch IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BWCH'] IS NOT NULL AND extras['BWCH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BWCD', SUM(CASE WHEN bwcd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BWCD'] IS NOT NULL AND extras['BWCD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BWCA', SUM(CASE WHEN bwca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BWCA'] IS NOT NULL AND extras['BWCA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'WHCH', SUM(CASE WHEN whch IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['WHCH'] IS NOT NULL AND extras['WHCH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'WHCD', SUM(CASE WHEN whcd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['WHCD'] IS NOT NULL AND extras['WHCD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'WHCA', SUM(CASE WHEN whca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['WHCA'] IS NOT NULL AND extras['WHCA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'PSCH', SUM(CASE WHEN psch IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['PSCH'] IS NOT NULL AND extras['PSCH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'PSCD', SUM(CASE WHEN pscd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['PSCD'] IS NOT NULL AND extras['PSCD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'PSCA', SUM(CASE WHEN psca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['PSCA'] IS NOT NULL AND extras['PSCA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'IWCH', SUM(CASE WHEN iwch IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['IWCH'] IS NOT NULL AND extras['IWCH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'IWCD', SUM(CASE WHEN iwcd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['IWCD'] IS NOT NULL AND extras['IWCD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'IWCA', SUM(CASE WHEN iwca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['IWCA'] IS NOT NULL AND extras['IWCA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'VCCH', SUM(CASE WHEN vcch IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['VCCH'] IS NOT NULL AND extras['VCCH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'VCCD', SUM(CASE WHEN vccd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['VCCD'] IS NOT NULL AND extras['VCCD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'VCCA', SUM(CASE WHEN vcca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['VCCA'] IS NOT NULL AND extras['VCCA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxCH', SUM(CASE WHEN maxch IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxCH'] IS NOT NULL AND extras['MaxCH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxCD', SUM(CASE WHEN maxcd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxCD'] IS NOT NULL AND extras['MaxCD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxCA', SUM(CASE WHEN maxca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxCA'] IS NOT NULL AND extras['MaxCA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgCH', SUM(CASE WHEN avgch IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgCH'] IS NOT NULL AND extras['AvgCH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgCD', SUM(CASE WHEN avgcd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgCD'] IS NOT NULL AND extras['AvgCD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgCA', SUM(CASE WHEN avgca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgCA'] IS NOT NULL AND extras['AvgCA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BFECH', SUM(CASE WHEN bfech IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BFECH'] IS NOT NULL AND extras['BFECH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BFECD', SUM(CASE WHEN bfecd IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BFECD'] IS NOT NULL AND extras['BFECD'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BFECA', SUM(CASE WHEN bfeca IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BFECA'] IS NOT NULL AND extras['BFECA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'B365C>2.5', SUM(CASE WHEN b365c_over_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['B365C>2.5'] IS NOT NULL AND extras['B365C>2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'B365C<2.5', SUM(CASE WHEN b365c_under_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['B365C<2.5'] IS NOT NULL AND extras['B365C<2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxC>2.5', SUM(CASE WHEN maxc_over_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxC>2.5'] IS NOT NULL AND extras['MaxC>2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxC<2.5', SUM(CASE WHEN maxc_under_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxC<2.5'] IS NOT NULL AND extras['MaxC<2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgC>2.5', SUM(CASE WHEN avgc_over_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgC>2.5'] IS NOT NULL AND extras['AvgC>2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgC<2.5', SUM(CASE WHEN avgc_under_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgC<2.5'] IS NOT NULL AND extras['AvgC<2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'PC>2.5', SUM(CASE WHEN pc_over_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['PC>2.5'] IS NOT NULL AND extras['PC>2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'PC<2.5', SUM(CASE WHEN pc_under_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['PC<2.5'] IS NOT NULL AND extras['PC<2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BFEC>2.5', SUM(CASE WHEN bfec_over_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BFEC>2.5'] IS NOT NULL AND extras['BFEC>2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BFEC<2.5', SUM(CASE WHEN bfec_under_25 IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BFEC<2.5'] IS NOT NULL AND extras['BFEC<2.5'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AHCh', SUM(CASE WHEN ahc_line IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AHCh'] IS NOT NULL AND extras['AHCh'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'B365CAHH', SUM(CASE WHEN b365c_ah_home IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['B365CAHH'] IS NOT NULL AND extras['B365CAHH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'B365CAHA', SUM(CASE WHEN b365c_ah_away IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['B365CAHA'] IS NOT NULL AND extras['B365CAHA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxCAHH', SUM(CASE WHEN maxc_ah_home IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxCAHH'] IS NOT NULL AND extras['MaxCAHH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxCAHA', SUM(CASE WHEN maxc_ah_away IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxCAHA'] IS NOT NULL AND extras['MaxCAHA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgCAHH', SUM(CASE WHEN avgc_ah_home IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgCAHH'] IS NOT NULL AND extras['AvgCAHH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgCAHA', SUM(CASE WHEN avgc_ah_away IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgCAHA'] IS NOT NULL AND extras['AvgCAHA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'PCAHH', SUM(CASE WHEN pc_ah_home IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['PCAHH'] IS NOT NULL AND extras['PCAHH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'PCAHA', SUM(CASE WHEN pc_ah_away IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['PCAHA'] IS NOT NULL AND extras['PCAHA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BFECAHH', SUM(CASE WHEN bfec_ah_home IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BFECAHH'] IS NOT NULL AND extras['BFECAHH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'BFECAHA', SUM(CASE WHEN bfec_ah_away IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['BFECAHA'] IS NOT NULL AND extras['BFECAHA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxAHH', SUM(CASE WHEN max_ah_home IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxAHH'] IS NOT NULL AND extras['MaxAHH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'MaxAHA', SUM(CASE WHEN max_ah_away IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['MaxAHA'] IS NOT NULL AND extras['MaxAHA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgAHH', SUM(CASE WHEN avg_ah_home IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgAHH'] IS NOT NULL AND extras['AvgAHH'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
    UNION ALL SELECT 'AvgAHA', SUM(CASE WHEN avg_ah_away IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN (extras['AvgAHA'] IS NOT NULL AND extras['AvgAHA'] <> '') THEN 1 ELSE 0 END) FROM raw_match_results
)
SELECT CAST(
    CASE
        WHEN SUM(CASE WHEN typed_count < extras_count THEN 1 ELSE 0 END) = 0 THEN '0'
        ELSE 'PHASE_B_AUDIT_FAILED__see_scripts/migration_002_audit_report.py_for_per_column_breakdown'
    END AS INTEGER
) AS phase_b_gate
FROM per_col;

-- ============================================================================
-- PHASE C — scrub promoted keys out of extras (irreversible without raw cache)
-- ============================================================================

-- DuckDB 1.5.x has no `map_filter`; use list_filter on entries + map_from_entries
-- to rebuild extras without the promoted keys.
UPDATE raw_match_results SET
    extras = map_from_entries(
        list_filter(map_entries(extras), e -> NOT list_contains([
            'B365CH','B365CD','B365CA',
            'BWCH','BWCD','BWCA',
            'WHCH','WHCD','WHCA',
            'PSCH','PSCD','PSCA',
            'IWCH','IWCD','IWCA',
            'VCCH','VCCD','VCCA',
            'MaxCH','MaxCD','MaxCA',
            'AvgCH','AvgCD','AvgCA',
            'BFECH','BFECD','BFECA',
            'B365C>2.5','B365C<2.5',
            'MaxC>2.5','MaxC<2.5',
            'AvgC>2.5','AvgC<2.5',
            'PC>2.5','PC<2.5',
            'BFEC>2.5','BFEC<2.5',
            'AHCh',
            'B365CAHH','B365CAHA',
            'MaxCAHH','MaxCAHA',
            'AvgCAHH','AvgCAHA',
            'PCAHH','PCAHA',
            'BFECAHH','BFECAHA',
            'MaxAHH','MaxAHA',
            'AvgAHH','AvgAHA'
        ], e.key))
    )
WHERE extras IS NOT NULL;

COMMIT;
