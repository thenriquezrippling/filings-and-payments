"""Tests for the LLM wrapper and prompts (Phase 2)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from tax_ops_filing_bot.llm.prompts import (
    build_extraction_messages,
    format_thread_for_prompt,
)
from tax_ops_filing_bot.llm.wrapper import AnthropicClient, LLMExtractionError
from tax_ops_filing_bot.models.schemas import FilingIssueDraft, FilingIssueCategory


class _SimpleModel(BaseModel):
    name: str
    value: int


class TestFormatThreadForPrompt:
    def test_basic_formatting(self) -> None:
        messages = [
            {"user": "U1", "text": "hello world", "ts": "1.0"},
            {"user": "U2", "text": "reply here", "ts": "2.0"},
        ]
        result = format_thread_for_prompt(messages)
        assert "[1] @U1: hello world" in result
        assert "[2] @U2: reply here" in result

    def test_empty_list(self) -> None:
        assert format_thread_for_prompt([]) == ""


class TestBuildExtractionMessages:
    def test_returns_user_message(self) -> None:
        msgs = build_extraction_messages("thread text here")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "thread text here" in msgs[0]["content"]


class TestAnthropicClientCompleteJson:
    def _make_client(self) -> AnthropicClient:
        return AnthropicClient(api_key="test-key")

    def _mock_response(self, text: str) -> MagicMock:
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.content = [block]
        return resp

    @patch("tax_ops_filing_bot.llm.wrapper.anthropic.Anthropic")
    def test_successful_parse(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._mock_response(
            json.dumps({"name": "test", "value": 42})
        )

        client = self._make_client()
        result = client.complete_json(
            [{"role": "user", "content": "hi"}],
            _SimpleModel,
        )
        assert result.name == "test"
        assert result.value == 42

    @patch("tax_ops_filing_bot.llm.wrapper.anthropic.Anthropic")
    def test_strips_markdown_fences(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        fenced = "```json\n{\"name\": \"fenced\", \"value\": 1}\n```"
        mock_client.messages.create.return_value = self._mock_response(fenced)

        client = self._make_client()
        result = client.complete_json(
            [{"role": "user", "content": "hi"}],
            _SimpleModel,
        )
        assert result.name == "fenced"

    @patch("tax_ops_filing_bot.llm.wrapper.anthropic.Anthropic")
    def test_retries_on_bad_json(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            self._mock_response("not json at all"),
            self._mock_response("still bad {"),
            self._mock_response(json.dumps({"name": "ok", "value": 1})),
        ]

        client = self._make_client()
        result = client.complete_json(
            [{"role": "user", "content": "hi"}],
            _SimpleModel,
        )
        assert result.name == "ok"
        assert mock_client.messages.create.call_count == 3

    @patch("tax_ops_filing_bot.llm.wrapper.anthropic.Anthropic")
    def test_raises_after_max_retries(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._mock_response("bad json!")

        client = self._make_client()
        with pytest.raises(LLMExtractionError, match="Failed to parse"):
            client.complete_json(
                [{"role": "user", "content": "hi"}],
                _SimpleModel,
            )

    @patch("tax_ops_filing_bot.llm.wrapper.anthropic.Anthropic")
    def test_non_text_block_raises(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        block = MagicMock()
        block.type = "tool_use"
        resp = MagicMock()
        resp.content = [block]
        mock_client.messages.create.return_value = resp

        client = self._make_client()
        with pytest.raises(LLMExtractionError, match="Unexpected content block"):
            client.complete_json(
                [{"role": "user", "content": "hi"}],
                _SimpleModel,
            )

    @patch("tax_ops_filing_bot.llm.wrapper.anthropic.Anthropic")
    def test_filing_issue_draft_parse(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        draft_json = json.dumps({
            "summary": "FLSUI blank SSNs in Q1 filing",
            "description": "Multiple files generated with blank SSNs.",
            "category": "missing_employee_data",
            "agency": "FLSUI",
            "priority": "P0",
            "labels": ["q1-2026", "peo"],
            "affected_entity_ids": ["FFID-123"],
            "suggested_dri": "haris",
            "confidence": 0.92,
        })
        mock_client.messages.create.return_value = self._mock_response(draft_json)

        client = self._make_client()
        result = client.complete_json(
            [{"role": "user", "content": "extract"}],
            FilingIssueDraft,
        )
        assert result.category == FilingIssueCategory.MISSING_EMPLOYEE_DATA
        assert result.priority == "P0"
        assert result.confidence == 0.92
