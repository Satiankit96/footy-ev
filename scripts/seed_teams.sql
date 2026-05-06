-- =========================================================================
-- seed_teams.sql
--
-- One-time bootstrap of the `teams` table from distinct team_ids in
-- team_aliases. Phase 1 prereq (DC fitting needs a stable canonical key per
-- club).
--
-- NOT auto-applied by apply_migrations(). Run once manually after migration
-- 004:
--
--   uv run python -c "import duckdb; con = duckdb.connect('data/warehouse/footy_ev.duckdb'); con.execute(open('scripts/seed_teams.sql').read())"
--
-- Re-run safe: ON CONFLICT (team_id) DO NOTHING. The aliases array is
-- aggregated from the raw_names we've seen across both sources; team_name
-- defaults to the football_data raw_name as a reasonable canonical display
-- string. Refine team_name and country (currently 'England' for EPL only)
-- when Phase 1 extends to other leagues.
-- =========================================================================

INSERT INTO teams (team_id, team_name, country, aliases, ingested_at)
SELECT
    team_id,
    team_name,
    'England'                AS country,
    aliases,
    CURRENT_TIMESTAMP        AS ingested_at
FROM (
    SELECT
        a.team_id,
        any_value(CASE WHEN a.source = 'football_data' THEN a.raw_name END) AS team_name,
        list(DISTINCT a.raw_name) AS aliases
    FROM team_aliases a
    GROUP BY a.team_id
) src
ON CONFLICT (team_id) DO NOTHING;
