-- =========================================================================
-- Migration 014: Add status column to kalshi_event_aliases.
--
-- The retire workflow appends a new row with status='retired' rather than
-- updating or deleting the original. The status column distinguishes
-- active from retired aliases.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS (DuckDB 0.8.0+).
-- =========================================================================

ALTER TABLE kalshi_event_aliases ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active';
