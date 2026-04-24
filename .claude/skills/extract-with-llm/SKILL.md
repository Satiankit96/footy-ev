---
name: extract-with-llm
description: Extract structured data from unstructured text using local Ollama or Gemini API fallback. Use for parsing injury reports, lineup news, tactical changes from articles/tweets.
---

# Structured extraction from text

Routing logic:
1. Read `LLM_EXTRACTOR` from `.env`. Default: `ollama`.
2. If `ollama`: call local Llama 3.1 8B via `ollama` Python client.
3. If `gemini` or if Ollama is down: call Gemini 2.5 Flash via `google-generativeai` with `GEMINI_API_KEY`.

Discipline:
- ALWAYS pass a JSON schema (pydantic model) to the LLM.
- ALWAYS validate the response with the pydantic model. Reject invalid output, retry once, then log and skip.
- ALWAYS canonicalize entity names (player names, team names) against the `players` and `teams` tables in DuckDB. Fuzzy-match with rapidfuzz, threshold ≥85.
- NEVER let raw LLM output reach the model feature pipeline. It must pass through `events_ledger` first.

When the operator asks to "extract X from this text," confirm the target schema first, then proceed.
