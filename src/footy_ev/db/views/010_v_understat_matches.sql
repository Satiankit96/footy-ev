-- =========================================================================
-- v_understat_matches: raw_understat_matches enriched with canonical team_ids.
--
-- Resolution policy: each match's home_team_raw / away_team_raw is left-joined
-- against team_aliases (source = 'understat') with a temporal filter
-- (kickoff_local within the alias's [active_from, active_to] window). The
-- temporal filter is future-proofing for mid-history team rebrands; bootstrap
-- aliases have NULL bounds (interpreted as "valid forever") so the filter is
-- a no-op in current data.
--
-- Failure mode: any unmapped raw_name yields NULL home_team_id / away_team_id.
-- The understat-detect-unmapped CLI surfaces these by joining the same way
-- and filtering for NULL team_ids. Downstream consumers MUST treat NULL ids
-- as a hard signal — joining through them silently drops rows.
--
-- Idempotent: CREATE OR REPLACE VIEW. Re-applying overwrites the prior
-- definition.
-- =========================================================================

CREATE OR REPLACE VIEW v_understat_matches AS
SELECT
    m.league,
    m.season,
    m.source_code,
    m.source_url,
    m.ingested_at,
    m.source_row_hash,
    m.understat_match_id,
    m.understat_home_id,
    m.understat_away_id,
    m.home_team_raw,
    m.away_team_raw,
    th.team_id        AS home_team_id,
    ta.team_id        AS away_team_id,
    m.kickoff_local,
    m.kickoff_utc,
    m.is_result,
    m.home_goals,
    m.away_goals,
    m.home_xg,
    m.away_xg,
    m.forecast_home_pct,
    m.forecast_draw_pct,
    m.forecast_away_pct,
    m.extras
FROM raw_understat_matches m
LEFT JOIN team_aliases th
    ON th.source = 'understat'
   AND th.raw_name = m.home_team_raw
   AND m.kickoff_local BETWEEN COALESCE(th.active_from, '1900-01-01'::TIMESTAMP)
                            AND COALESCE(th.active_to,   '9999-12-31'::TIMESTAMP)
LEFT JOIN team_aliases ta
    ON ta.source = 'understat'
   AND ta.raw_name = m.away_team_raw
   AND m.kickoff_local BETWEEN COALESCE(ta.active_from, '1900-01-01'::TIMESTAMP)
                            AND COALESCE(ta.active_to,   '9999-12-31'::TIMESTAMP);
