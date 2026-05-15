"""Tests for services: command parsing, IntakeService, SyncService (Phase 3)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.jira.client import JiraClient
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft, IssueType
from tax_ops_filing_bot.models.thread import NormalizedThread, ThreadMessage
from tax_ops_filing_bot.services.commands import parse_sync_command, SyncCommand
from tax_ops_filing_bot.services.intake import IntakeService, IntakeResult
from tax_ops_filing_bot.services.sync import SyncService, SyncResult


def _make_thread(n: int = 3, text_template: str = "Message about filing {i}") -> NormalizedThread:
    return NormalizedThread(
        channel_id="C001",
        thread_ts="1715000000.000100",
        messages=[
            ThreadMessage(
                user_id=f"U{i}",
                username=f"user{i}",
                text=text_template.format(i=i),
                ts=f"{1715000000 + i}.000100",
            )
            for i in range(n)
        ],
    )


def _pittsburgh_eit_thread() -> NormalizedThread:
    """Simulate a real Pittsburgh EIT thread."""
    return NormalizedThread(
        channel_id="C001",
        thread_ts="1715000000.000100",
        messages=[
            ThreadMessage(
                user_id="U1",
                username="tony",
                text="Pittsburgh EIT filing is blocked — the portal is rejecting our submission",
                ts="1715000000.000100",
            ),
            ThreadMessage(
                user_id="U2",
                username="alice",
                text="This is blocking payroll for 200+ employees, need resolution ASAP",
                ts="1715000001.000100",
            ),
            ThreadMessage(
                user_id="U3",
                username="bob",
                text="I'll reach out to the city tax office today",
                ts="1715000002.000100",
            ),
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
        assert result.draft.summary

    def test_pittsburgh_eit_classified_as_blocker(self) -> None:
        """Pittsburgh EIT thread must be classified as Blocker with correct epic."""
        llm = AnthropicClient(api_key="mock")
        svc = IntakeService(llm)
        thread = _pittsburgh_eit_thread()
        result = svc.infer_draft(thread)
        assert result.draft.issue_type == IssueType.BLOCKER
        assert result.draft.parent_key == "FILING-101"
        assert "local-tax" in result.draft.labels
        assert "pittsburgh" in result.draft.labels

    def test_deterministic_work_type_applied(self) -> None:
        llm = AnthropicClient(api_key="mock")
        svc = IntakeService(llm)
        thread = _make_thread(2, text_template="feature request: add bulk upload {i}")
        result = svc.infer_draft(thread)
        assert result.draft.issue_type == IssueType.FEATURE_REQUEST

    def test_deterministic_epic_mapped(self) -> None:
        llm = AnthropicClient(api_key="mock")
        svc = IntakeService(llm)
        thread = _make_thread(2, text_template="quarterly filing for Q1 is late {i}")
        result = svc.infer_draft(thread)
        assert result.draft.parent_key == "FILING-200"

    def test_deterministic_labels_generated(self) -> None:
        llm = AnthropicClient(api_key="mock")
        svc = IntakeService(llm)
        thread = _make_thread(2, text_template="urgent federal filing deadline {i}")
        result = svc.infer_draft(thread)
        assert "urgent" in result.draft.labels
        assert "federal" in result.draft.labels
        assert "deadline" in result.draft.labels

    def test_retro_classification(self) -> None:
        llm = AnthropicClient(api_key="mock")
        svc = IntakeService(llm)
        thread = _make_thread(2, text_template="retrospective on Q4 missed filing {i}")
        result = svc.infer_draft(thread)
        assert result.draft.issue_type == IssueType.RETRO

    def test_executive_summary_classification(self) -> None:
        llm = AnthropicClient(api_key="mock")
        svc = IntakeService(llm)
        thread = _make_thread(2, text_template="weekly status report for tax ops team {i}")
        result = svc.infer_draft(thread)
        assert result.draft.issue_type == IssueType.EXECUTIVE_SUMMARY


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
