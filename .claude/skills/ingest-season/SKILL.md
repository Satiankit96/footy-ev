---
name: ingest-season
description: Idempotently ingest one season of historical data for one league. Use when the operator says "ingest season X for league Y" or wants to backfill data.
---

# Ingest a single season for one league

When invoked:

1. Validate the season format: must be "YYYY-YYYY" with consecutive years.
2. Validate the league: must be one of EPL, LL, SA, BL, L1.
3. Run: `make ingest-season SEASON=$SEASON LEAGUE=$LEAGUE`
4. After completion, verify row counts:
   - football-data.co.uk match results: should be 380 (EPL/LL/SA), 306 (BL), 380 (L1)
   - If row count is materially off, STOP and report. Do not retry blindly.
5. Run the freshness audit: `uv run python -m footy_ev.ingestion.audit --season $SEASON --league $LEAGUE`
6. Report success with row counts per source.

Be polite to data sources: ≥2s between Understat requests, ≥3s between FBref requests.
Re-running this skill on a season that's already ingested must be a no-op (idempotency check via UPSERT or hash).
