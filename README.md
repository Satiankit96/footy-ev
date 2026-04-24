# footy-ev

Local-first +EV sports betting pipeline for European football. Free-tier edition.

## Quick start

```bash
make install
make check-stack
```

## Stack

All free:
- Claude Pro for the IDE agent
- Gemini 2.5 Pro (student) as overflow + NotebookLM for paper review
- GitHub Pro (Student Pack) for repo + Copilot + Codespaces
- DuckDB + Parquet for storage
- Betfair Exchange Delayed API + football-data.co.uk + Understat + FBref for data
- Ollama (Llama 3.1 8B) for parsing, with Gemini API as fallback

See:
- `CLAUDE.md` — project conventions Claude Code follows automatically
- `BLUE_MAP.md` — architecture spec
- `PROJECT_INSTRUCTIONS.md` — full operator brief
- `SETUP_GUIDE.md` — step-by-step workflow
- `COSTS.md` — confirmation that this is all free

## Status

Phase 0: scaffold. No business logic yet.
