-- =========================================================================
-- scripts/seed_team_aliases.sql
--
-- ONE-TIME OPERATOR-RUN BOOTSTRAP. NOT a migration. NOT auto-applied by
-- apply_migrations(). Seeds team_aliases with the 70 rows needed to resolve
-- every (source, raw_name) pair that appears in raw_match_results AND
-- raw_understat_matches across EPL 2014-15 → 2025-26.
--
-- Re-run safety: the file ends with ON CONFLICT (source, raw_name) DO NOTHING,
-- so applying it twice is a no-op. Existing rows are not overwritten — if you
-- need to update an alias, do so manually.
--
-- Coverage scope: 35 EPL teams × 2 sources (football_data + understat) = 70 rows.
-- This covers every team that appeared in either source from 2014-15 onward.
--
-- Adding new seasons: when a future season introduces a promoted team whose
-- raw_name is not yet here, APPEND a new INSERT statement to this file (do not
-- create a new seed file). Keep the file in alphabetical-by-team_id order.
--
-- Asymmetric pairs (different raw_name spellings between sources, called out
-- inline below for clarity): man_city, man_united, newcastle, nottm_forest,
-- qpr, west_brom, wolves.
--
-- canonical team_id = lower snake_case of the football_data spelling.
-- =========================================================================

-- 35 football_data raw_name → team_id mappings
INSERT INTO team_aliases (source, raw_name, team_id, confidence, resolved_at, active_from, active_to, notes) VALUES
    ('football_data', 'Arsenal',          'arsenal',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Aston Villa',      'aston_villa',      'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Bournemouth',      'bournemouth',      'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Brentford',        'brentford',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Brighton',         'brighton',         'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Burnley',          'burnley',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Cardiff',          'cardiff',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Chelsea',          'chelsea',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Crystal Palace',   'crystal_palace',   'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Everton',          'everton',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Fulham',           'fulham',           'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Huddersfield',     'huddersfield',     'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Hull',             'hull',             'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Ipswich',          'ipswich',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Leeds',            'leeds',            'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Leicester',        'leicester',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Liverpool',        'liverpool',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Luton',            'luton',            'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Man City',         'man_city',         'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: understat = "Manchester City"
    ('football_data', 'Man United',       'man_united',       'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: understat = "Manchester United"
    ('football_data', 'Middlesbrough',    'middlesbrough',    'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Newcastle',        'newcastle',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: understat = "Newcastle United"
    ('football_data', 'Norwich',          'norwich',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Nott''m Forest',   'nottm_forest',     'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: understat = "Nottingham Forest"; SQL apostrophe escape
    ('football_data', 'QPR',              'qpr',              'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: understat = "Queens Park Rangers"
    ('football_data', 'Sheffield United', 'sheffield_united', 'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Southampton',      'southampton',      'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Stoke',            'stoke',            'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Sunderland',       'sunderland',       'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Swansea',          'swansea',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Tottenham',        'tottenham',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Watford',          'watford',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'West Brom',        'west_brom',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: understat = "West Bromwich Albion"
    ('football_data', 'West Ham',         'west_ham',         'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('football_data', 'Wolves',           'wolves',           'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward')   -- asymmetric: understat = "Wolverhampton Wanderers"
ON CONFLICT (source, raw_name) DO NOTHING;

-- 35 understat raw_name → team_id mappings (same canonical team_ids)
INSERT INTO team_aliases (source, raw_name, team_id, confidence, resolved_at, active_from, active_to, notes) VALUES
    ('understat', 'Arsenal',                 'arsenal',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Aston Villa',             'aston_villa',      'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Bournemouth',             'bournemouth',      'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Brentford',               'brentford',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Brighton',                'brighton',         'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Burnley',                 'burnley',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Cardiff',                 'cardiff',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Chelsea',                 'chelsea',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Crystal Palace',          'crystal_palace',   'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Everton',                 'everton',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Fulham',                  'fulham',           'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Huddersfield',            'huddersfield',     'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Hull',                    'hull',             'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Ipswich',                 'ipswich',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Leeds',                   'leeds',            'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Leicester',               'leicester',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Liverpool',               'liverpool',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Luton',                   'luton',            'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Manchester City',         'man_city',         'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: football_data = "Man City"
    ('understat', 'Manchester United',       'man_united',       'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: football_data = "Man United"
    ('understat', 'Middlesbrough',           'middlesbrough',    'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Newcastle United',        'newcastle',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: football_data = "Newcastle"
    ('understat', 'Norwich',                 'norwich',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Nottingham Forest',       'nottm_forest',     'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: football_data = "Nott'm Forest"
    ('understat', 'Queens Park Rangers',     'qpr',              'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: football_data = "QPR"
    ('understat', 'Sheffield United',        'sheffield_united', 'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Southampton',             'southampton',      'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Stoke',                   'stoke',            'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Sunderland',              'sunderland',       'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Swansea',                 'swansea',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Tottenham',               'tottenham',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Watford',                 'watford',          'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'West Bromwich Albion',    'west_brom',        'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),  -- asymmetric: football_data = "West Brom"
    ('understat', 'West Ham',                'west_ham',         'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward'),
    ('understat', 'Wolverhampton Wanderers', 'wolves',           'manual', CURRENT_TIMESTAMP, NULL, NULL, 'Bootstrap seed for EPL 2014-15 onward')   -- asymmetric: football_data = "Wolves"
ON CONFLICT (source, raw_name) DO NOTHING;
