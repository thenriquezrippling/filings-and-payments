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


class TestSystemPrompt:
    def test_mentions_filing_project(self) -> None:
        assert "FILING" in SYSTEM_PROMPT

    def test_mentions_json(self) -> None:
        assert "JSON" in SYSTEM_PROMPT
