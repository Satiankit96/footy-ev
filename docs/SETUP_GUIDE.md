# Setup Guide

Operator-facing setup steps that aren't fully automated by the code.

## Betfair Exchange — Delayed Application Key (free tier)

The paper-trading runtime in [`runtime/paper_trader.py`](../src/footy_ev/runtime/paper_trader.py)
needs three things from Betfair: an account (free), a Delayed Application
Key (free, instant), and your username/password. No deposit, no real-money
betting in this phase.

### 1. Open a Betfair Exchange account

1. Go to [betfair.com](https://www.betfair.com/) and register a real
   account. You will need to confirm an email and possibly do a basic
   identity check (passport / address). This is mandated for any
   regulated UK gambling site even if you never deposit.
2. **Do not deposit money.** Real-money betting is gated on PROJECT_INSTRUCTIONS §3
   bankroll discipline, which we are not at yet.

### 2. Request a Delayed Application Key

1. Sign in at [developer-docs.betfair.com](https://developer-docs.betfair.com/).
2. Open the **Application Keys** tool (left sidebar).
3. Click **Create Application Key**, give it a name (e.g. `footy-ev-paper`),
   and select **Delayed**. The Delayed key is free and rate-limited; data
   is approximately 60 seconds behind the live exchange. That latency is
   fine for paper trading and CLV measurement; it is not fine for
   in-running arbitrage (which we are not doing).
4. Copy the resulting key (32-char hex string).

### 3. Populate `.env`

```env
BETFAIR_APP_KEY=<your delayed key>
BETFAIR_USERNAME=<your betfair login email>
BETFAIR_PASSWORD=<your betfair password>
# BETFAIR_CERT_PATH is optional. The Delayed-key flow uses simple
# username/password login. Cert login only matters once you upgrade
# to a Live key, which is Phase 4+.
```

`.env` is gitignored. Confirm with `git check-ignore .env`. Never commit
this file or paste credentials into an LLM session.

### 4. Verify the credentials work

```powershell
$env:FOOTY_EV_BETFAIR_LIVE = "1"
.\make.ps1 test-integration
# tests/integration/test_betfair_live.py runs a single read-only listEvents
# call against the real Delayed API. Skips with a clear message if either
# the env var or any BETFAIR_* var is missing.
```

A passing live test confirms login + the three calls (`listEvents`,
`listMarketCatalogue`, `listMarketBook`) reach Betfair successfully.

### 5. Start the paper trader

```powershell
python run.py paper-trade --once
# Single-pass smoke test: pulls upcoming EPL fixtures, runs the LangGraph
# once per fixture, writes any approved bets to paper_bets.

python run.py paper-trade --fixtures-ahead-days 7
# Continuous mode: polls every 5 minutes, ctrl-C to stop. Safe to resume;
# state is checkpointed to data/langgraph_checkpoints.sqlite.

python run.py paper-status
# Prints latest invocation, recent paper bets, breaker status.
```

## What if I don't have a Betfair account yet?

The implementation works without one. All unit and graph integration
tests use mocked Betfair responses. Only `test_betfair_live.py` requires
the real account — and it skips cleanly when `FOOTY_EV_BETFAIR_LIVE` is
unset or any `BETFAIR_*` env var is empty. The paper-trade runtime will
fail at startup with a clear "missing BETFAIR_APP_KEY" message; once the
key is added it just works.
