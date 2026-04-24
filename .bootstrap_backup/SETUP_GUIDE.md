# Claude Code Setup Guide — Free-Tier Edition

> How to drop the project into VS Code and let Claude Pro take over without burning your token budget, plus how to use Gemini Pro and Copilot as overflow.

---

## Part 1 — Mental Model First (Read Before Touching the Keyboard)

Claude Code in VS Code is **not** a chat window with file access. It is an autonomous agent that reads files, edits them, runs your shell, executes your tests, and commits your code. Treating it like ChatGPT will make you fight the tool.

There are five layers of context Claude Code uses, in priority order:

1. **`CLAUDE.md`** at the project root — read at the start of every session, *always-on* context. Keep under ~200 lines or you waste tokens every turn.
2. **`@-mentioned files`** in your prompt — explicitly pulled in when you reference them.
3. **Skills** in `.claude/skills/` — on-demand context Claude loads when a task matches a skill's description.
4. **Subagents** in `.claude/agents/` — workers Claude spawns to do isolated work in their own context window.
5. **MCP servers** — external tool access (databases, APIs, file stores).

**On Pro specifically**, two things matter more than they would on Max:

- **Skills > big CLAUDE.md.** Anything that's not relevant to every task should be a skill, not always-on context. Always-on context burns tokens every single turn.
- **Subagents save your main session.** When you tell Claude "scrape Understat for 10 seasons," that work generates huge intermediate context. A subagent does it in its own window and only returns a summary. Without subagents your main session fills up and you hit limits twice as fast.

---

## Part 2 — Your Multi-LLM Stack

You have access to several AI tools, all free. The goal is to use each for what it's best at and **never run two agentic tools on the same codebase simultaneously** — they'll fight each other.

| Tool | Cost to You | When to Use | Key Limits |
|---|---|---|---|
| **Claude Code (Pro)** | $20/mo (already paid) | Primary IDE agent. Multi-file work, planning with Opus, running tests, commits. | ~44K tokens per 5h window |
| **Claude.ai web chat** | Included in Pro | Architecture discussions, code review *without* burning Code-side tokens | Same 5h window shared with Code |
| **GitHub Copilot Pro** | Free (Student Pack) | Tab completion while typing; Copilot Chat for quick questions | 300 premium requests/month for Chat; unlimited tab completion |
| **Copilot Chat w/ Opus** | Free (part of Copilot Pro) | Second Opus opinion when Claude is rate-limited, or adversarial review of Claude's plan | Opus requests cost ~5 premium reqs each, so ~60 Opus requests/month |
| **Gemini 2.5 Pro (student)** | Free for 12 months | Overflow when both Claude and Copilot premium are exhausted; one-shot codegen | Generous free limits |
| **NotebookLM (Gemini Pro)** | Free (with Gemini Pro) | Literature synthesis. Drop papers in, ask questions grounded in them. | Not for code |
| **Gemini 2.5 Flash API** | Free (aistudio.google.com) | Automated extraction tasks (tweets, articles) when Ollama too slow | ~1500 req/day |
| **Ollama + Llama 3.1 8B** | Free, local | Parsing unstructured text into JSON, offline | Needs ≥16GB RAM |

### The optimal split

**Claude Code is your primary agent.** Everything that touches the codebase multi-file goes through here. Don't cross the streams with Copilot agent mode.

**Copilot inline tab completion is always on.** It fills in boilerplate while you type — class scaffolds, imports, routine pydantic models. This costs you nothing and saves Claude tokens.

**Copilot Chat (300/month) is your quick-question pool.** When you have a simple question you don't want to burn a Claude session on: "explain this regex," "what's the time complexity," "why is this throwing TypeError." Use it inline in VS Code via the Copilot Chat panel.

**Copilot Chat with Opus (~60/month) is your emergency reserve.** Use when:
- Claude Pro is rate-limited and you need Opus-tier reasoning *now*
- You want a second Opus opinion on Claude's plan before committing to it (adversarial review catches bugs)
- A hard architectural call where you want two independent Opus perspectives

**Gemini 2.5 Pro web is your unlimited overflow.** When everything else is exhausted, paste the prompt into Gemini, copy the result back when Claude resets.

**NotebookLM is your research assistant.** Drop Dixon-Coles 1997, Karlis-Ntzoufras, Wilkens 2026 into a notebook. Ask conceptual questions there. Don't burn Claude tokens asking "what does the tau parameter do in Dixon-Coles" when NotebookLM can answer it with citations.

### The workflow, step by step

1. **Architecture discussion** → Claude.ai web chat (uses Pro quota but doesn't interrupt Code sessions)
2. **Plan implementation** → Claude Code with `/model opus` (short planning session only)
3. **Implement** → Claude Code with `/model sonnet`
4. **Tab completion while typing** → Copilot inline (always on)
5. **Quick question during coding** → Copilot Chat (cheap premium request)
6. **Hit Claude rate limit on a hard architectural question** → Copilot Chat w/ Opus
7. **Hit Claude rate limit on a code task** → Gemini 2.5 Pro web, paste back later
8. **Research conceptual ML/stats question** → NotebookLM
9. **Parse text into structured JSON** → Ollama (or Gemini Flash API if laptop weak)

### The trap to avoid

**Do not enable Copilot agent mode while Claude Code is running on the same repo.** Both will try to edit files. You'll get conflicting edits, wasted tokens on both sides, and confusion about which tool made which change. Pick Claude Code as your agent and use Copilot for completion + chat only.

---

## Part 3 — The Hand-Off Workflow (Step by Step)

### Step 0: Confirm your stack is ready

You need:
- **Claude Pro** ($20/mo, already paid) — gives Claude Code access
- **Gemini Pro (student)** — confirm at gemini.google.com that "Pro" shows in account
- **GitHub Pro (Student Developer Pack)** — confirm at education.github.com/pack
- **Copilot Pro** — auto-included with Student Pack; activate at github.com/settings/copilot

If any of these aren't active, sort them out before installing anything else.

### Step 1: Install Claude Code CLI

```bash
# macOS / Linux
curl -fsSL https://claude.ai/install.sh | sh

# or via npm
npm install -g @anthropic-ai/claude-code

# Verify
claude --version
```

### Step 2: Install VS Code extensions

Open VS Code → Extensions → install:
- **Claude Code** (publisher: Anthropic)
- **GitHub Copilot** (publisher: GitHub)
- **GitHub Copilot Chat** (publisher: GitHub) — optional, useful for inline questions

### Step 3: Authenticate Claude Code against Pro

```bash
claude
```

On first run it opens a browser for OAuth. **Critical gotcha:** if you have `ANTHROPIC_API_KEY` set in your environment, Claude Code will use the API key (pay-per-token) instead of your Pro subscription, which means you'd be billed in addition to your subscription. Check:

```bash
echo $ANTHROPIC_API_KEY  # if it prints anything, unset it
unset ANTHROPIC_API_KEY
```

If you need an API key for any reason later (e.g., a script that uses Claude), put it in `.env` and load it explicitly in that script — not in your shell profile.

### Step 4: Activate Copilot Pro and configure to not interfere with Claude

Copilot is fine for boilerplate but can be visually noisy. Configure it to be less aggressive in your VS Code workspace settings (the `bootstrap.sh` script handles this):

- Disable inline suggestions in Markdown files (so you can write `CLAUDE.md` in peace)
- Keep tab completion in `.py` files

### Step 5: Get a free Gemini API key (for parsing tasks)

1. Go to aistudio.google.com → Get API Key
2. Create a key in a new project
3. Save it for later — we'll put it in `.env` to use as Ollama fallback

The free tier of Gemini API is genuinely generous (millions of tokens/day for Gemini 2.5 Flash). It's a great fallback when Ollama is too slow on your laptop.

### Step 6: Create the project and run the bootstrap

**Important: follow this exact order or you'll overwrite your own files.**

```bash
mkdir -p ~/projects/footy-ev
cd ~/projects/footy-ev
```

Drop ONLY `bootstrap.sh` into the folder first. Then:

```bash
bash bootstrap.sh .
# The "." means "bootstrap into the current directory"
```

This creates the directory tree, dependency manifest, Makefile, `.gitignore`, `.claudeignore`, Claude Code settings, VS Code workspace settings, three starter skills, two starter subagents, a passing smoke test, and a minimal `CLAUDE.md` + `README.md`.

**Now overlay your real files.** Drop these four at the project root, letting them overwrite the bootstrap's stubs:

- `CLAUDE.md` (yours is richer than bootstrap's stub — overwrite it)
- `PROJECT_INSTRUCTIONS.md`
- `BLUE_MAP.md`
- `SETUP_GUIDE.md` (this file, for your reference)
- `COSTS.md`

Verify:

```bash
make install
make check-stack
```

`make check-stack` verifies Python works, tells you if Ollama is installed (optional), checks for `.env`, and runs the smoke tests. If it's green, you're ready.

### Step 7: Run `/init` once to let Claude scan and propose its own additions

```bash
cd ~/projects/footy-ev
make install   # uv sync
make test      # smoke test should pass
claude         # launch Claude Code
```

In the Claude Code session:

```
/init
```

This makes Claude scan your project structure and propose additions to `CLAUDE.md`. **Important:** review what it suggests carefully on Pro — you don't want a 600-line `CLAUDE.md` burning tokens every session. Accept only what's actually project-specific (build commands, test conventions). Reject anything generic (it's already in your `CLAUDE.md`).

### Step 8: First contact — verify Claude read the docs

Before giving Claude any real task, do a sanity check:

```
Read CLAUDE.md, skim PROJECT_INSTRUCTIONS.md and BLUE_MAP.md §1–§3.
Then confirm in 3 bullet points:
  (a) what's the project mission in one sentence,
  (b) what are three banned paths,
  (c) what phase are we starting.
If any of those are unclear, ask. Don't write any code.
```

If Claude's answer is accurate, you're good. If it hallucinates or misses obvious things from the docs, something's wrong — check that files are actually at the project root and not in a subfolder.

### Step 9: First real handoff — token-conscious version

```
/model opus

Read CLAUDE.md, PROJECT_INSTRUCTIONS.md (skim), BLUE_MAP.md §1, §6, §8.

I want to implement Phase 0 step 1: ingestion of football-data.co.uk historical match odds for EPL only (one league, to start small).

Source URL pattern:
  https://www.football-data.co.uk/mmz4281/{season}/E0.csv
where season is "2425" for 2024-2025.

Enter plan mode. Produce a plan covering:
  1. The DuckDB raw_match_results schema (mirror source CSV columns).
  2. A Pydantic model for one row.
  3. Ingestion function signature with httpx + tenacity retries.
  4. Idempotency: re-running ingestion is a no-op.
  5. Tests we need (unit + integration).

Be concise. Show me the plan only. I will critique. We implement after approval.
```

After you approve the plan:

```
/model sonnet
Implement step 1 (the schema). Run tests. Stop.
```

Then:

```
Implement step 2 (the Pydantic model). Run tests. Stop.
```

This staccato pattern keeps each Claude turn small and bounded. On Pro this is critical — you might do 5 of these turns before the next prompt needs to wait for window reset.

---

## Part 4 — File Placement Cheat Sheet

What goes where, and why:

```
~/projects/footy-ev/
├── CLAUDE.md                      ← always-on context, ~150 lines max
├── PROJECT_INSTRUCTIONS.md        ← human reference; Claude reads on demand
├── BLUE_MAP.md                    ← architecture spec; Claude reads on demand
├── SETUP_GUIDE.md                 ← this file, for you not Claude
├── COSTS.md                       ← reference, all $0 in your case
├── .claude/
│   ├── skills/
│   │   ├── run-backtest/SKILL.md
│   │   ├── ingest-season/SKILL.md
│   │   └── audit-clv/SKILL.md
│   ├── agents/
│   │   ├── data-scraper.md        ← isolated subagent for scraping
│   │   └── backtest-runner.md     ← isolated subagent for long backtests
│   └── settings.json              ← auto-approve, deny-list, hooks
├── .claudeignore                  ← excludes data/, .venv/, *.parquet
├── .gitignore
├── .vscode/settings.json          ← VS Code workspace config
├── pyproject.toml
├── Makefile
├── src/
├── tests/
├── data/                          ← .gitignored, .claudeignored
├── notebooks/
└── reports/
```

Three principles:

1. **`CLAUDE.md` is the manifest, not the manual.** It points to longer docs, doesn't replace them. "For full architecture, see `BLUE_MAP.md`" is the right pattern. If `CLAUDE.md` is 800 lines, every session burns 800 lines of tokens before you've said hello. On Pro this matters more than on Max.

2. **Skills are for repeatable workflows, not one-off tasks.** "Implement Dixon-Coles" is a request, not a skill. "Run a walk-forward backtest with these standard arguments" is a skill — you'll do it dozens of times.

3. **Subagents protect your main context window.** When you tell Claude "scrape Understat for 10 seasons," spawn a subagent. The scraping work happens in its own window and only a summary returns. This is how you stretch Pro's token budget further.

---

## Part 5 — When You Hit a Rate Limit

You will hit Pro's limits, especially during Phase 0 when there's a lot of plumbing. Here's the playbook:

### Immediate response

The error message tells you when the window resets ("Resets at HH:MM"). Two options:

**Option A: Switch to Gemini for the same task.**
1. Open gemini.google.com (or aistudio.google.com)
2. Paste the prompt you were about to send
3. Copy Gemini's response
4. When Claude resets, paste Gemini's answer back as: "I asked Gemini to handle this while you were rate-limited. Here's what it produced. Review it for correctness, integrate into the codebase, and run tests."

This works great for code generation tasks (write a function), less well for agentic tasks (refactor 5 files). Gemini doesn't know your codebase the way Claude does after a long session.

**Option B: Use the wait time productively.**
- Read the next paper on the reading list (Dixon-Coles, Karlis-Ntzoufras)
- Hand-debug the most recent thing Claude built
- Sketch the next phase on paper
- Refactor by hand using Copilot tab completion only

Either is fine. Don't try to "trick" the rate limit — it doesn't work and Anthropic's anti-abuse will eventually flag you.

### Preventing future rate limits

- **One topic per session, then `/clear`.** Don't let a session balloon.
- **`@-mention files sparingly.** If Claude already has `models/dixon_coles.py` in context, don't `@models/dixon_coles.py` it again.
- **Use Sonnet by default.** Only switch to Opus for planning.
- **Don't ask Claude to "explain" things you can read.** Save Claude for tasks that need it to use tools (read, edit, run).

---

## Part 6 — Codespaces as Backup

Your GitHub Student Pack includes 180 core-hours/month of Codespaces — cloud VS Code with a full dev environment. This is useful when:

- Your laptop is too slow to run the full stack
- You want to work from a public computer
- You want a clean, reproducible dev environment

To use:
1. Push your repo to GitHub (private)
2. Click "Code" → "Codespaces" → "Create codespace on main"
3. The repo opens in a browser-based VS Code
4. Install Claude Code in the Codespace terminal: `npm install -g @anthropic-ai/claude-code`
5. Authenticate with your Pro account

Codespaces uses your same Pro quota for Claude Code — it doesn't give you "more Claude," but it gives you "more compute on which to run Claude."

---

## Part 7 — Important Settings and Hooks

The `bootstrap.sh` script creates these for you. Quick reference:

### `.claude/settings.json` (auto-approve safe commands, deny dangerous ones)

```json
{
  "permissions": {
    "auto_approve": [
      "Read", "Glob", "Grep",
      "Bash(make test*)", "Bash(make lint)", "Bash(make typecheck)",
      "Bash(uv run pytest*)"
    ],
    "deny": [
      "Bash(rm -rf*)",
      "Bash(git push --force*)",
      "Bash(*LIVE_TRADING=true*)",
      "Write(.env)", "Edit(.env)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "uv run ruff format \"$CLAUDE_FILE_PATH\" 2>/dev/null && uv run ruff check --fix \"$CLAUDE_FILE_PATH\" 2>/dev/null || true"
      }
    ]
  }
}
```

The deny-list is your safety net. Don't disable it.

### `.claudeignore`

Keeps Claude from accidentally trying to read 5GB Parquet files into context.

### VS Code workspace settings (`.vscode/settings.json`)

Auto-save at 1000ms is critical — if VS Code holds unsaved buffer changes, Claude operates on stale content and its edits collide with unsaved editor state.

---

## Part 8 — How to Actually Drive a Session (The Etiquette)

The skills below are what separates "Claude wrote me a working backtest in 30 minutes" from "I spent 3 days fighting Claude and gave up."

### Always plan before implementing on anything > 1 file

```
/model opus
I want to add isotonic calibration to the Dixon-Coles output.
Enter plan mode. Show me the files you'd touch, the new files you'd add, the tests you'd write.
Do not implement until I approve. Be concise.
```

Plan mode forces Claude to think before acting. The cost of a bad plan compounds — fixing structural mistakes after implementation is 10× the work of catching them in the plan.

### Use `/clear` aggressively

When you finish one logical chunk of work and start another, run `/clear`. On Pro this matters more than on Max — every kilobyte of stale context shortens the time until your next rate-limit hit.

### Use `/compact` mid-task when context fills

If you're in the middle of one logical chunk but the context is getting full, `/compact` summarizes the conversation so far into a shorter context, freeing space.

### Challenge Claude on its own work

When Claude says "I've implemented the Kelly sizing module," your next message should not be "great, what's next." It should be:

```
Walk me through the Kelly sizing implementation as if you were code-reviewing it for a senior engineer who wants to fail you. What are three ways this could be wrong? What edge cases are uncovered by tests?
```

This adversarial pattern catches bugs and overclaiming far better than asking Claude to "review the code" (which produces sycophantic agreement).

### Never let Claude ship without tests

The simplest hook to add to `CLAUDE.md`:

> **Test discipline:** No new function ships without a test. No bug fix ships without a regression test. The acceptance criterion for any task is "tests pass" not "code looks right."

### Use git as your safety net

Commit before any large refactor. Claude can and will sometimes mass-edit your files in ways that break things subtly. `git restore .` is a one-keystroke escape hatch.

---

## Part 9 — Subscription & Cost Reality (See COSTS.md)

For your situation, the full breakdown is in `COSTS.md`. Quick view:

| What | Cost | How |
|---|---|---|
| Claude Pro | Already paid | Yours |
| Gemini Pro | Free | Student plan — confirm at gemini.google.com |
| GitHub Pro + Copilot Pro + DigitalOcean $200 + Codespaces 180 hrs | Free | Student Developer Pack at education.github.com |
| Betfair Exchange API | Free | Free Delayed Application Key (1-min delay, perfect for dev) |
| All data sources | Free | football-data.co.uk, Understat scrape, FBref scrape |
| Cloud hosting (Phase 3+) | Free | Oracle Cloud Free Tier (4 vCPU, 24GB RAM forever) OR DigitalOcean from Student credit |
| Compute burst | Free | Google Colab Free + Kaggle 30 GPU hrs/wk |

**Total ongoing cost: $0/month** (you're already paying Claude Pro).

---

## Part 10 — The "Don't Do This" List

Free-tier specific additions to standard Claude Code best practices:

1. **Don't put your Betfair API credentials in `CLAUDE.md` or any file Claude can read.** Use `.env` (gitignored, claudeignored) and load via `os.getenv()`. Even better, use the OS keychain via `keyring`.

2. **Don't let Claude run live bet placement during development.** Hard-gate execution with the `LIVE_TRADING=true` env var; default is paper-only. The deny-list in `settings.json` blocks Claude from setting this var.

3. **Don't use `/auto` mode for trading-adjacent code.** Auto-approve is fine for refactors; for anything that touches money calculations, demand explicit approval.

4. **Don't ask Claude to "improve" working code.** Vague refactor requests produce churn without value. Be specific: "Add type hints to `kelly_stake`" not "improve `kelly_stake`."

5. **Don't keep one giant Claude Code session running for hours.** On Pro, this is rate-limit suicide. One session per logical unit of work; `/clear` between them.

6. **Don't trust Claude's claims of "I've tested this."** It hallucinates test runs sometimes. Your eyes on `pytest` output are the only proof tests pass.

7. **Don't skip the data-leakage audit.** Periodically (every ~10 sessions) ask: "Audit this codebase for any feature that could leak data from after match kickoff into a pre-match prediction. Be paranoid." This catches the single most common bug in backtest pipelines.

8. **Don't try to do "agentic" work in Gemini.** Gemini 2.5 Pro is excellent for one-shot tasks but doesn't have the same tool-use discipline as Claude. Use Gemini for code generation when Claude's rate-limited; come back to Claude for any task involving file editing, running tests, or multi-step reasoning.

9. **Don't waste Copilot.** It's free and excellent at boilerplate. If you're typing `def __init__(self, ` there's no reason to ask Claude — let Copilot autocomplete and save your Claude tokens for harder problems.

10. **Don't deploy Phase 4 until you have real disposable bankroll.** I will keep saying this because it's the most important rule. The system can be perfect; if your bankroll is your rent money, variance will destroy you in the first 200 bets.
