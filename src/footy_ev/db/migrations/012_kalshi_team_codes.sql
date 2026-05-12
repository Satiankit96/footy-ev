-- =========================================================================
-- Migration 012: 3-letter EPL team-code aliases.
--
-- Kalshi event tickers encode teams as 3-letter codes
-- (e.g. KXEPLTOTAL-26MAY24WHULEE → WHU=West Ham, LEE=Leeds).
-- Bootstrap resolves these via team_aliases with source='kalshi_code'.
--
-- This migration seeds the 20 current Premier League team codes.
-- Lookup: SELECT team_id FROM team_aliases WHERE source='kalshi_code' AND raw_name=?
--
-- Idempotent: INSERT OR IGNORE on (source, raw_name) PK.
-- =========================================================================

INSERT OR IGNORE INTO team_aliases (source, raw_name, team_id, confidence, resolved_at)
VALUES
    ('kalshi_code', 'ARS', 'arsenal',        'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'AVL', 'aston_villa',    'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'BHA', 'brighton',       'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'BOU', 'bournemouth',    'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'BRE', 'brentford',      'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'BUR', 'burnley',        'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'CHE', 'chelsea',        'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'CRY', 'crystal_palace', 'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'EVE', 'everton',        'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'FUL', 'fulham',         'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'LEE', 'leeds',          'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'LIV', 'liverpool',      'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'MCI', 'man_city',       'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'MUN', 'man_united',     'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'NEW', 'newcastle',      'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'NFO', 'nottm_forest',   'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'SUN', 'sunderland',     'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'TOT', 'tottenham',      'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'WHU', 'west_ham',       'manual', TIMESTAMP '2026-05-12 00:00:00'),
    ('kalshi_code', 'WOL', 'wolves',         'manual', TIMESTAMP '2026-05-12 00:00:00');
