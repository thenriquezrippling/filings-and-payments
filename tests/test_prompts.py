"""Tests for LLM prompt construction."""

from __future__ import annotations

from tax_ops_filing_bot.llm.prompts import SYSTEM_PROMPT, build_messages


class TestBuildMessages:
    def test_returns_single_user_message(self) -> None:
        msgs = build_messages(channel="test", thread_text="hello world")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_includes_channel_name(self) -> None:
        msgs = build_messages(channel="filing-review", thread_text="some text")
        assert "#filing-review" in msgs[0]["content"]

    def test_includes_thread_text(self) -> None:
        msgs = build_messages(channel="ch", thread_text="EIT Pittsburgh 1Q2026")
        assert "EIT Pittsburgh 1Q2026" in msgs[0]["content"]

    def test_asks_for_llm_extraction_schema(self) -> None:
        msgs = build_messages(channel="ch", thread_text="text")
        assert "LLMExtraction" in msgs[0]["content"]


class TestSystemPrompt:
    def test_mentions_filing_project(self) -> None:
        assert "FILING" in SYSTEM_PROMPT

    def test_mentions_json(self) -> None:
        assert "JSON" in SYSTEM_PROMPT

    def test_prohibits_implementation_notes(self) -> None:
        assert "tests pass" in SYSTEM_PROMPT
        assert "lint is clean" in SYSTEM_PROMPT
        assert "I implemented" in SYSTEM_PROMPT

    def test_asks_for_state_abbreviation(self) -> None:
        assert "state" in SYSTEM_PROMPT.lower()
        assert "two-letter" in SYSTEM_PROMPT.lower()

    def test_asks_for_impact_scope(self) -> None:
        assert "impact_scope" in SYSTEM_PROMPT

    def test_asks_for_ff_client_id(self) -> None:
        assert "ff_client_id" in SYSTEM_PROMPT
