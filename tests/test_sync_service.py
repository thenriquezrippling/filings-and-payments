"""Tests for Jira <-> Slack thread synchronization.

Covers:
  - Ticket creation posts Sync [FILING-KEY] in Slack thread
  - Sync-only command posts Sync [FILING-KEY]
  - Sync-only command does NOT create a new Jira issue
  - Jira comments include Slack metadata (channel, thread_ts, permalink)
  - Duplicate sync markers are not posted
  - Duplicate Jira comments are not added
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tax_ops_filing_bot.services.sync_service import (
    SyncResult,
    SyncService,
    build_jira_comment_adf,
    build_jira_comment_body,
    build_sync_marker,
    jira_has_thread_comment,
    parse_sync_command,
    thread_has_sync_marker,
)


def _mock_slack(existing_messages: list[dict] | None = None):
    slack = MagicMock()
    slack.conversations_replies.return_value = {
        "messages": existing_messages or [],
    }
    slack.chat_postMessage.return_value = {"ok": True}
    return slack


def _mock_jira(existing_comments: list[dict] | None = None):
    jira = MagicMock()
    jira.get_comments.return_value = existing_comments or []
    jira.add_comment.return_value = {"id": "90001"}
    return jira


class TestParseSyncCommand:
    def test_basic(self) -> None:
        assert parse_sync_command("sync this thread to FILING-1234") == "FILING-1234"

    def test_with_mention(self) -> None:
        assert parse_sync_command("<@U123> sync this thread to FILING-42") == "FILING-42"

    def test_case_insensitive(self) -> None:
        assert parse_sync_command("Sync This Thread To filing-99") == "FILING-99"

    def test_no_match(self) -> None:
        assert parse_sync_command("please create a ticket") is None


class TestBuildSyncMarker:
    def test_format(self) -> None:
        assert build_sync_marker("FILING-1234") == "Sync [FILING-1234]"


class TestThreadHasSyncMarker:
    def test_found(self) -> None:
        msgs = [{"text": "Sync [FILING-1234]"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is True

    def test_not_found(self) -> None:
        msgs = [{"text": "Hello world"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is False

    def test_different_key_not_matched(self) -> None:
        msgs = [{"text": "Sync [FILING-5555]"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is False


class TestJiraHasThreadComment:
    def test_found_in_adf_comment(self) -> None:
        comments = [
            {
                "body": {
                    "content": [
                        {"content": [{"type": "text", "text": "Thread timestamp: 123.456"}]}
                    ]
                }
            }
        ]
        assert jira_has_thread_comment(comments, "123.456") is True

    def test_not_found(self) -> None:
        comments = [
            {
                "body": {
                    "content": [
                        {"content": [{"type": "text", "text": "Some other comment"}]}
                    ]
                }
            }
        ]
        assert jira_has_thread_comment(comments, "123.456") is False


class TestBuildJiraCommentBody:
    def test_includes_channel(self) -> None:
        body = build_jira_comment_body(
            channel="C001", thread_ts="123.456", transcript="hello",
        )
        assert "C001" in body
        assert "123.456" in body

    def test_includes_permalink(self) -> None:
        body = build_jira_comment_body(
            channel="C001", thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
            transcript="hello",
        )
        assert "https://slack.com/archives/C001/p123456" in body

    def test_includes_transcript(self) -> None:
        body = build_jira_comment_body(
            channel="C001", thread_ts="123.456", transcript="EIT issue found",
        )
        assert "EIT issue found" in body


class TestSyncServiceAfterCreation:
    """Post-creation sync: Slack marker + Jira comment."""

    def test_posts_sync_marker(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.sync_marker_posted is True
        slack.chat_postMessage.assert_called_once()
        call_kwargs = slack.chat_postMessage.call_args
        assert "Sync [FILING-1234]" in call_kwargs.kwargs.get("text", "")

    def test_adds_jira_comment(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.jira_comment_added is True
        jira.add_comment.assert_called_once()
        comment_text = jira.add_comment.call_args[0][1]
        assert "C001" in comment_text
        assert "123.456" in comment_text

    def test_jira_comment_includes_permalink(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
            transcript="EIT issue found",
        )
        comment_text = jira.add_comment.call_args[0][1]
        assert "https://slack.com/archives/C001/p123456" in comment_text


class TestSyncServiceSyncOnly:
    """Sync-only command: add context to existing Jira issue, no new issue."""

    def test_sync_only_posts_marker(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira)

        result = svc.sync_existing(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.sync_marker_posted is True
        assert result.jira_comment_added is True
        assert result.issue_key == "FILING-1234"

    def test_sync_only_does_not_create_jira_issue(self) -> None:
        """sync_existing must NOT call create_issue."""
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira)

        svc.sync_existing(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert not hasattr(jira, "create_issue") or not jira.create_issue.called


class TestSyncDeduplication:
    """Duplicate sync markers and Jira comments are not added."""

    def test_duplicate_sync_marker_not_posted(self) -> None:
        slack = _mock_slack(
            existing_messages=[{"text": "Sync [FILING-1234]"}],
        )
        jira = _mock_jira()
        svc = SyncService(slack, jira)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.skipped_marker is True
        assert result.sync_marker_posted is False
        slack.chat_postMessage.assert_not_called()

    def test_duplicate_jira_comment_not_added(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira(
            existing_comments=[
                {
                    "body": {
                        "content": [
                            {"content": [{"type": "text", "text": "Thread timestamp: 123.456"}]}
                        ]
                    }
                }
            ],
        )
        svc = SyncService(slack, jira)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.skipped_comment is True
        assert result.jira_comment_added is False
        jira.add_comment.assert_not_called()

    def test_both_already_exist(self) -> None:
        slack = _mock_slack(
            existing_messages=[{"text": "Sync [FILING-1234]"}],
        )
        jira = _mock_jira(
            existing_comments=[
                {
                    "body": {
                        "content": [
                            {"content": [{"type": "text", "text": "Thread timestamp: 123.456"}]}
                        ]
                    }
                }
            ],
        )
        svc = SyncService(slack, jira)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.skipped_marker is True
        assert result.skipped_comment is True
        slack.chat_postMessage.assert_not_called()
        jira.add_comment.assert_not_called()
