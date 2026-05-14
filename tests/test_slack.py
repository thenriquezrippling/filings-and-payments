"""Tests for Slack blocks, thread_fetch, and app handlers (Phase 4)."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from tax_ops_filing_bot.models.schemas import (
    AgencyCode,
    FilingIssueDraft,
    FilingIssueCategory,
)
from tax_ops_filing_bot.slack.blocks import (
    draft_confirmation_blocks,
    error_blocks,
    issue_created_blocks,
    sync_success_blocks,
)
from tax_ops_filing_bot.slack.thread_fetch import fetch_thread, parse_sync_command


class TestDraftConfirmationBlocks:
    def test_produces_blocks(self) -> None:
        draft = FilingIssueDraft(
            summary="FLSUI blank SSNs",
            description="Test description with details",
            category=FilingIssueCategory.MISSING_EMPLOYEE_DATA,
            agency=AgencyCode.FLSUI,
            priority="P0",
            labels=["q1-2026"],
            affected_entity_ids=["FFID-123"],
            suggested_dri="haris",
            confidence=0.9,
        )
        blocks = draft_confirmation_blocks(draft, "1234.5678")
        assert len(blocks) > 0

        block_types = [b["type"] for b in blocks]
        assert "header" in block_types
        assert "actions" in block_types

        actions_block = next(b for b in blocks if b["type"] == "actions")
        action_ids = [e["action_id"] for e in actions_block["elements"]]
        assert "filing_create_confirm" in action_ids
        assert "filing_create_cancel" in action_ids

    def test_no_agency(self) -> None:
        draft = FilingIssueDraft(
            summary="Generic issue",
            description="Desc",
            category=FilingIssueCategory.OTHER,
            confidence=0.5,
        )
        blocks = draft_confirmation_blocks(draft, "1.0")
        text_content = json.dumps(blocks)
        assert "N/A" in text_content

    def test_truncates_long_description(self) -> None:
        draft = FilingIssueDraft(
            summary="Long desc",
            description="x" * 5000,
            category=FilingIssueCategory.OTHER,
            confidence=0.5,
        )
        blocks = draft_confirmation_blocks(draft, "1.0")
        text_content = json.dumps(blocks)
        assert "..." in text_content


class TestIssueCreatedBlocks:
    def test_contains_key(self) -> None:
        blocks = issue_created_blocks("FILING-9999", "Test summary")
        text = json.dumps(blocks)
        assert "FILING-9999" in text
        assert "Test summary" in text


class TestSyncSuccessBlocks:
    def test_contains_count(self) -> None:
        blocks = sync_success_blocks("FILING-100", 15)
        text = json.dumps(blocks)
        assert "FILING-100" in text
        assert "15" in text


class TestErrorBlocks:
    def test_contains_error(self) -> None:
        blocks = error_blocks("Something bad happened")
        text = json.dumps(blocks)
        assert "Something bad happened" in text


class TestParseSyncCommand:
    def test_basic_sync(self) -> None:
        assert parse_sync_command("sync this thread to FILING-5911") == "FILING-5911"

    def test_with_mention(self) -> None:
        result = parse_sync_command("<@U123> sync this thread to FILING-100")
        assert result == "FILING-100"

    def test_case_insensitive(self) -> None:
        result = parse_sync_command("Sync This Thread To FILING-200")
        assert result == "FILING-200"

    def test_no_match(self) -> None:
        assert parse_sync_command("just a regular message") is None

    def test_create_message_no_match(self) -> None:
        assert parse_sync_command("create a ticket from this thread") is None


class TestFetchThread:
    def test_fetch_thread(self) -> None:
        mock_client = MagicMock()
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"user": "U1", "text": "parent msg", "ts": "1000.0"},
                {"user": "U2", "text": "reply 1", "ts": "1001.0"},
                {"user": "U3", "text": "reply 2", "ts": "1002.0"},
            ]
        }
        mock_client.chat_getPermalink.return_value = {
            "permalink": "https://slack.com/link/1"
        }

        ctx = fetch_thread(mock_client, "C123", "1000.0")
        assert ctx.channel_id == "C123"
        assert ctx.thread_ts == "1000.0"
        assert len(ctx.messages) == 3
        assert ctx.messages[0].text == "parent msg"
        assert ctx.permalink == "https://slack.com/link/1"

    def test_fetch_thread_permalink_failure(self) -> None:
        mock_client = MagicMock()
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"user": "U1", "text": "msg", "ts": "1.0"},
            ]
        }
        mock_client.chat_getPermalink.side_effect = Exception("API error")

        ctx = fetch_thread(mock_client, "C1", "1.0")
        assert ctx.permalink is None
        assert len(ctx.messages) == 1


class TestCreateApp:
    def test_create_app_missing_env(self) -> None:
        """create_app requires env vars; verify it raises without them."""
        with pytest.raises(KeyError):
            from tax_ops_filing_bot.slack.app import create_app
            create_app()

    @patch.dict(os.environ, {
        "SLACK_BOT_TOKEN": "xoxb-test",
        "JIRA_BASE_URL": "https://test.atlassian.net",
        "JIRA_EMAIL": "bot@test.com",
        "JIRA_API_TOKEN": "fake-token",
        "JIRA_PROJECT_KEY": "FILING",
        "ANTHROPIC_API_KEY": "sk-test",
    })
    @patch("tax_ops_filing_bot.slack.app.App")
    @patch("tax_ops_filing_bot.slack.app.JiraClient")
    @patch("tax_ops_filing_bot.slack.app.AnthropicClient")
    def test_create_app_registers_listeners(
        self,
        _mock_anthropic: MagicMock,
        _mock_jira: MagicMock,
        mock_app_cls: MagicMock,
    ) -> None:
        from tax_ops_filing_bot.slack.app import create_app

        create_app()
        mock_app = mock_app_cls.return_value
        assert mock_app.event.called or mock_app.action.called
