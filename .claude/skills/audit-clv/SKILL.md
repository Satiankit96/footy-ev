---
name: audit-clv
description: Audit recent paper-trading or live-trading bets for closing line value. Use when the operator asks "how am I doing on CLV" or wants a CLV report.
---

# CLV audit

When invoked:

1. Default lookback is 30 days; accept an override.
2. Query the `bet_decisions` table for status='settled' AND placed_at >= NOW() - INTERVAL '30 days'.
3. Compute CLV per bet: `(odds_taken / closing_odds) - 1`.
4. Report:
   - Total settled bets
   - Mean CLV (%) and 95% CI via bootstrap (1000 resamples)
   - CLV by market type (1X2, OU2.5, BTTS, AH)
   - CLV by venue
   - Bets where odds_taken < closing_odds (negative CLV) — should be the minority
5. If mean CLV is negative AND the bootstrap lower bound is below 0, raise a flag: edge appears to be gone.
6. Output report to `reports/clv_audit_$DATE.md`.

Never silently exclude "outliers." If a bet looks anomalous, list it but include it.
