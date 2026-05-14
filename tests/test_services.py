"""Tests for IntakeService and SyncService (Phase 3)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tax_ops_filing_bot.jira.client import JiraIssue
from tax_ops_filing_bot.models.schemas import (
    FilingIssueDraft,
    FilingIssueCategory,
    SyncRequest,
    ThreadContext,
    ThreadMessage,
)
from tax_ops_filing_bot.services.intake import IntakeResult, IntakeService
from tax_ops_filing_bot.services.sync import SyncService


def _make_thread(n: int = 3) -> ThreadContext:
    return ThreadContext(
        channel_id="C123",
        thread_ts="1000.000000",
        messages=[
            ThreadMessage(user=f"U{i}", text=f"msg {i}", ts=f"100{i}.000000")
            for i in range(n)
        ],
        permalink="https://slack.com/thread/1",
    )


def _make_draft(**overrides: object) -> FilingIssueDraft:
    defaults: dict = {
        "summary": "Test issue",
        "description": "Test description",
        "category": FilingIssueCategory.MISSING_EMPLOYEE_DATA,
        "priority": "P1",
        "confidence": 0.8,
    }
    defaults.update(overrides)
    return FilingIssueDraft(**defaults)


class TestIntakeService:
    def test_extract_draft(self) -> None:
        mock_llm = MagicMock()
        mock_jira = MagicMock()
        expected_draft = _make_draft()
        mock_llm.complete_json.return_value = expected_draft

        svc = IntakeService(llm=mock_llm, jira=mock_jira)
        thread = _make_thread()
        result = svc.extract_draft(thread)

        assert result == expected_draft
        mock_llm.complete_json.assert_called_once()

    def test_create_issue(self) -> None:
        mock_llm = MagicMock()
        mock_jira = MagicMock()
        mock_jira.create_issue.return_value = JiraIssue(
            key="FILING-100",
            id="10001",
            self_url="https://test.atlassian.net/rest/api/3/issue/10001",
        )

        svc = IntakeService(llm=mock_llm, jira=mock_jira)
        draft = _make_draft(labels=["q1-2026"])
        thread = _make_thread()
        issue = svc.create_issue(draft, thread)

        assert issue.key == "FILING-100"
        mock_jira.create_issue.assert_called_once()
        call_kwargs = mock_jira.create_issue.call_args
        assert "q1-2026" in call_kwargs.kwargs["labels"]

    def test_create_issue_appends_permalink(self) -> None:
        mock_llm = MagicMock()
        mock_jira = MagicMock()
        mock_jira.create_issue.return_value = JiraIssue(
            key="FILING-101", id="10002", self_url="url"
        )

        svc = IntakeService(llm=mock_llm, jira=mock_jira)
        draft = _make_draft()
        thread = _make_thread()
        svc.create_issue(draft, thread)

        call_args = mock_jira.create_issue.call_args
        description = call_args.kwargs["description"]
        assert "https://slack.com/thread/1" in description

    def test_intake_no_auto_create(self) -> None:
        mock_llm = MagicMock()
        mock_jira = MagicMock()
        mock_llm.complete_json.return_value = _make_draft()

        svc = IntakeService(llm=mock_llm, jira=mock_jira)
        result = svc.intake(_make_thread(), auto_create=False)

        assert isinstance(result, IntakeResult)
        assert result.draft is not None
        assert result.jira_issue is None
        assert result.confirmed is False
        mock_jira.create_issue.assert_not_called()

    def test_intake_auto_create(self) -> None:
        mock_llm = MagicMock()
        mock_jira = MagicMock()
        mock_llm.complete_json.return_value = _make_draft()
        mock_jira.create_issue.return_value = JiraIssue(
            key="FILING-200", id="10003", self_url="url"
        )

        svc = IntakeService(llm=mock_llm, jira=mock_jira)
        result = svc.intake(_make_thread(), auto_create=True)

        assert result.confirmed is True
        assert result.jira_issue is not None
        assert result.jira_issue.key == "FILING-200"


class TestSyncService:
    def test_sync_posts_comment(self) -> None:
        mock_jira = MagicMock()
        mock_jira.add_comment.return_value = {"id": "comment-1"}

        svc = SyncService(jira=mock_jira)
        thread = _make_thread()
        request = SyncRequest(issue_key="FILING-5911", thread=thread)
        result = svc.sync(request)

        assert result["id"] == "comment-1"
        mock_jira.add_comment.assert_called_once()
        call_args = mock_jira.add_comment.call_args
        assert call_args[0][0] == "FILING-5911"
        body = call_args[0][1]
        assert "C123" in body
        assert "@U0" in body

    def test_sync_includes_permalink(self) -> None:
        mock_jira = MagicMock()
        mock_jira.add_comment.return_value = {"id": "comment-2"}

        svc = SyncService(jira=mock_jira)
        thread = _make_thread()
        request = SyncRequest(issue_key="FILING-100", thread=thread)
        svc.sync(request)

        body = mock_jira.add_comment.call_args[0][1]
        assert "https://slack.com/thread/1" in body
