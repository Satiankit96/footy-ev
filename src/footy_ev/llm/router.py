"""Router for LLM extraction tasks: prefer Ollama, fall back to Gemini."""

from __future__ import annotations

import os
from typing import Literal

LLMProvider = Literal["ollama", "gemini"]


def select_provider() -> LLMProvider:
    """Return the configured provider, defaulting to ollama."""
    val = os.getenv("LLM_EXTRACTOR", "ollama").lower()
    if val not in {"ollama", "gemini"}:
        raise ValueError(f"LLM_EXTRACTOR must be 'ollama' or 'gemini', got {val!r}")
    return val  # type: ignore[return-value]


if __name__ == "__main__":
    provider = select_provider()
    print(f"LLM extractor selected: {provider}")
