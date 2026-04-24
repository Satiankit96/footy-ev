# Costs Sheet — footy-ev (Free-Tier Edition)

> Total ongoing cost: $0/month. You're already paying Claude Pro; everything else is free.
> This file documents what each free service gives you and the limits to be aware of.

---

## What You Already Have

| Tool | Cost | What You Get | Limits to Know |
|---|---|---|---|
| **Claude Pro** | Already paid ($20/mo) | Claude Code in terminal/VS Code, Claude.ai web chat, Opus 4.7 + Sonnet 4.6 | ~44K tokens per 5h window. Plan with Opus, implement with Sonnet to stretch budget |
| **Gemini Pro (Student)** | Free for 12 months | Gemini 2.5 Pro web/API, NotebookLM Pro, 2TB Google Drive, Gemini in Workspace | API free tier: ~1500 req/day on Gemini 2.5 Flash; lower on 2.5 Pro |
| **GitHub Pro (Student Pack)** | Free while a student | Private repos, Copilot Pro, Codespaces 180 hrs/mo, $200 DigitalOcean credit, lots more | Renew yearly through education.github.com |

That's the entire LLM and IDE budget. Nothing else needed.

---

## The Free Data Stack

This is the entire data layer at zero cost. None of these are inferior to paid alternatives — they're what professional bettors actually use.

| Source | Cost | What You Get | Access Method | Limits |
|---|---|---|---|---|
| **football-data.co.uk** | Free | 25+ seasons of match results + opening/closing odds across major books for top 5 leagues | Direct CSV download | None published; be polite |
| **Understat** | Free | Per-shot xG, xA for top 5 leagues from 2014–15 onward | Web scrape with Playwright | ≥2s between requests |
| **FBref (Sports Reference)** | Free | Comprehensive team/player stats, advanced metrics, set-piece data | Web scrape | ≥3s between requests, respect robots.txt |
| **OpenFootball** (github.com/openfootball) | Free | Fixtures, results, structured football data | Direct GitHub clone | None |
| **Football-Data.org** | Free tier | Fixtures, current standings, basic match info | API key (free signup) | 10 req/min |
| **The Odds API** | Free tier | Cross-book odds aggregation | API key (free signup) | 500 req/month |
| **Betfair Exchange API** | Free (Delayed key) | Real-time-ish odds with 1-min delay; perfect for development and paper trading | Free Betfair account + free Application Key via developer portal | 1-min delay on free tier; live key is ~£299 one-time but you don't need it until Phase 4 |
| **Reddit r/soccer + Twitter/X** | Free with care | Late-breaking news, lineup leaks | snscrape or similar | Very aggressive rate limiting required |

---

## Free Hosting Options (Phase 3+)

You don't need this until you want 24/7 odds polling without your laptop on. When you do:

| Option | Cost | Notes |
|---|---|---|
| **Old laptop / Raspberry Pi at home** | Free if you have one | Plug in, run the polling loop, done. Most reliable. |
| **Oracle Cloud Free Tier** | Free forever | 4 ARM vCPUs, 24GB RAM permanently free. Sign up before they change the offering. More than enough. |
| **DigitalOcean (Student Pack credit)** | Effectively free | $200 credit lasts 33 months on a $6/mo droplet |
| **GitHub Codespaces** | Free 180 hrs/mo | Browser-based VS Code with full dev env. Useful when laptop is weak or you're working from public computers |

---

## Free Compute for Heavy Backtests

When your laptop is too slow:

| Option | Cost | Best For |
|---|---|---|
| **Google Colab Free** | Free | Walk-forward backtests, training XGBoost models |
| **Kaggle Notebooks** | Free | 30 GPU hours/week — overkill for this project but available |
| **Codespaces** | Free 180 hrs/mo | Faster CPU than your laptop probably has |

---

## Local LLM Options

For parsing tweets, injury reports, lineups into structured JSON:

| Option | Cost | When to Use |
|---|---|---|
| **Ollama + Llama 3.1 8B** | Free | If your laptop has ≥16GB RAM. Runs offline. |
| **Ollama + Qwen 2.5 7B** | Free | Alternative; sometimes better at JSON output |
| **Ollama + Llama 3.2 3B** | Free | If laptop has only 8GB RAM. Lower quality but works. |
| **Gemini 2.5 Flash via free API** | Free (1500 req/day) | If laptop too weak for Ollama, or if you want better extraction quality |

Recommendation: Try Ollama first. Fall back to Gemini Flash API if your laptop chokes.

---

## What You're Explicitly NOT Buying

I want to call these out so you don't feel like you're "missing something":

- **Pinnacle Odds Dropper ($39/mo)** — Replaced by using Betfair Exchange Starting Price as your CLV benchmark. Functionally equivalent for the goal of "is my model beating the sharp close."
- **API-Sports / API-Football ($19+/mo)** — Replaced by FBref scraping. More maintenance work but free.
- **OddsJam ($159+/mo)** — Only relevant for player props (Phase 2+); you're starting with team markets where the free Betfair Exchange data is sufficient.
- **Claude Max ($100+/mo)** — Pro is enough for this project. Token discipline is the workaround.
- **Cloud GPUs (RunPod, Lambda)** — Colab and Kaggle are free and sufficient for XGBoost. You're not training neural nets.
- **VPN services for "geo unlocking"** — Don't. This violates ToS at every venue.
- **"AI Pick" subscriptions** — These are the exact thing you're building. Buying them defeats the purpose.

---

## When You Eventually Want to Spend Money

Here's the honest order of upgrades, if/when you can afford them, ranked by ROI on actual betting performance:

1. **Disposable bankroll first** ($200–500). Until you have this, no other spend matters because you can't go live.
2. **Claude Max 5x** ($100/mo). Buy when you're spending more than 2 hours/day waiting for Pro to reset.
3. **Pinnacle Odds Dropper** ($39/mo). Buy when you have a working pipeline and want a sharper benchmark.
4. **Betfair Live App Key** (£299 one-time). Buy when you're ready for real-time odds (live trading). Not before.
5. **API-Sports** ($19/mo). Buy when scraper maintenance is eating more than 4 hrs/month of your time.

But seriously: don't buy anything until the system shows positive CLV on a 1000+ bet paper sample. Until then, every dollar spent is a dollar that should be in the bankroll instead.

---

## Quick Total

**Today:** $0 ongoing (Claude Pro already paid)
**Phase 4 ready:** $0 ongoing (free Betfair Delayed key works for paper trading)
**Phase 4 live:** £299 one-time for Betfair Live App Key + a bankroll you can afford to lose 50% of
**Scale-up (post-graduation):** Same as paid version in original `COSTS.md`

The constraint on this project is your time and discipline, not your money.
