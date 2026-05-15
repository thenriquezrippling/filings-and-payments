"""Tests for the LLM wrapper and prompts (Phase 2)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from tax_ops_filing_bot.llm.prompts import build_messages, SYSTEM_PROMPT, USER_TEMPLATE
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft, IssuePriority


class TestPrompts:
    def test_build_messages_structure(self) -> None:
        msgs = build_messages("hello world")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "hello world" in msgs[1]["content"]

    def test_system_prompt_content(self) -> None:
        assert "FILING" in SYSTEM_PROMPT
        assert "summary" in SYSTEM_PROMPT
        assert "JSON" in SYSTEM_PROMPT
        assert "Blocker" in SYSTEM_PROMPT
        assert "Filing Exception" in SYSTEM_PROMPT
        assert "Feature Request" in SYSTEM_PROMPT
        assert "Retro" in SYSTEM_PROMPT
        assert "Executive Summary" in SYSTEM_PROMPT

    def test_user_template_substitution(self) -> None:
        rendered = USER_TEMPLATE.format(thread_text="My tax thread")
        assert "My tax thread" in rendered


class TestAnthropicClientMock:
    def test_mock_mode_with_sentinel(self) -> None:
        client = AnthropicClient(api_key="mock")
        assert client.is_mock

    def test_mock_mode_with_empty_string(self) -> None:
        client = AnthropicClient(api_key="")
        assert client.is_mock

    def test_mock_returns_defaults(self) -> None:
        client = AnthropicClient(api_key="mock")
        draft = client.complete_json([], FilingIssueDraft)
        assert isinstance(draft, FilingIssueDraft)
        assert draft.summary  # should be a placeholder string, not empty
        assert draft.description

    def test_mock_preserves_explicit_defaults(self) -> None:
        client = AnthropicClient(api_key="mock")
        draft = client.complete_json([], FilingIssueDraft)
        assert draft.priority == IssuePriority.MEDIUM
        assert draft.labels == []

    def test_real_mode_flag(self) -> None:
        client = AnthropicClient(api_key="sk-ant-real")
        assert not client.is_mock


class _SimpleModel(BaseModel):
    name: str
    count: int = 5


class TestBuildDefault:
    def test_fills_required_str(self) -> None:
        result = AnthropicClient._build_default(_SimpleModel)
        assert isinstance(result, _SimpleModel)
        assert "<name>" in result.name
        assert result.count == 5

    def test_fills_required_int(self) -> None:
        class M(BaseModel):
            value: int

        result = AnthropicClient._build_default(M)
        assert result.value == 0
