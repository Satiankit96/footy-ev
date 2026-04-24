"""Test LLM provider selection."""

import pytest

from footy_ev.llm.router import select_provider


def test_default_is_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_EXTRACTOR", raising=False)
    assert select_provider() == "ollama"


def test_gemini_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_EXTRACTOR", "gemini")
    assert select_provider() == "gemini"


def test_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_EXTRACTOR", "openai")
    with pytest.raises(ValueError, match="must be"):
        select_provider()
