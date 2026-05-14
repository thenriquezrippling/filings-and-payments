"""Tests for services: command parsing, IntakeService, SyncService (Phase 3)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.jira.client import JiraClient
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft
from tax_ops_filing_bot.models.thread import NormalizedThread, ThreadMessage
from tax_ops_filing_bot.services.commands import parse_sync_command, SyncCommand
from tax_ops_filing_bot.services.intake import IntakeService, IntakeResult
from tax_ops_filing_bot.services.sync import SyncService, SyncResult


def _make_thread(n: int = 3) -> NormalizedThread:
    return NormalizedThread(
        channel_id="C001",
        thread_ts="1715000000.000100",
        messages=[
            ThreadMessage(
                user_id=f"U{i}",
                username=f"user{i}",
                text=f"Message about filing {i}",
                ts=f"{1715000000 + i}.000100",
            )
            for i in range(n)
        ],
    )


class TestParseSyncCommand:
    def test_basic_sync(self) -> None:
        result = parse_sync_command("sync this thread to FILING-1234")
        assert result is not None
        assert result.issue_key == "FILING-1234"

    def test_with_mention_prefix(self) -> None:
        result = parse_sync_command("<@U12345> sync this thread to FILING-42")
        assert result is not None
        assert result.issue_key == "FILING-42"

    def test_case_insensitive(self) -> None:
        result = parse_sync_command("Sync This Thread To filing-99")
        assert result is not None
        assert result.issue_key == "FILING-99"

    def test_no_match_plain_text(self) -> None:
        result = parse_sync_command("please create a ticket for this")
        assert result is None

    def test_no_match_partial(self) -> None:
        result = parse_sync_command("sync this thread")
        assert result is None

    def test_different_project_key(self) -> None:
        result = parse_sync_command("sync this thread to TAX-5")
        assert result is not None
        assert result.issue_key == "TAX-5"

    def test_frozen_dataclass(self) -> None:
        cmd = SyncCommand(issue_key="FILING-1")
        with pytest.raises(Exception):
            cmd.issue_key = "FILING-2"  # type: ignore[misc]


class TestIntakeService:
    def test_infer_draft_mock(self) -> None:
        llm = AnthropicClient(api_key="mock")
        svc = IntakeService(llm)
        thread = _make_thread(3)
        result = svc.infer_draft(thread)
        assert isinstance(result, IntakeResult)
        assert isinstance(result.draft, FilingIssueDraft)
        assert result.thread is thread
        assert result.draft.summary  # placeholder from mock


class TestSyncService:
    def test_sync_thread_success(self) -> None:
        jira = JiraClient(base_url="mock")
        svc = SyncService(jira)
        thread = _make_thread(2)
        result = svc.sync_thread(thread, "FILING-42")
        assert isinstance(result, SyncResult)
        assert result.success
        assert result.issue_key == "FILING-42"
        assert result.comment_id

    def test_sync_preserves_issue_key(self) -> None:
        jira = JiraClient(base_url="mock")
        svc = SyncService(jira)
        thread = _make_thread(1)
        result = svc.sync_thread(thread, "TAX-7")
        assert result.issue_key == "TAX-7"
