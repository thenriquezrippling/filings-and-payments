"""Tests for Pydantic models (Phase 2)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.models.thread import ThreadMessage, NormalizedThread
from tax_ops_filing_bot.models.issue_draft import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
)


class TestThreadMessage:
    def test_basic_construction(self) -> None:
        msg = ThreadMessage(user_id="U123", username="alice", text="hello", ts="1715000000.000100")
        assert msg.user_id == "U123"
        assert msg.username == "alice"
        assert msg.text == "hello"

    def test_datetime_utc(self) -> None:
        msg = ThreadMessage(user_id="U1", text="test", ts="1715000000.000100")
        dt = msg.datetime_utc
        assert dt.year == 2024
        assert dt.tzname() == "UTC"

    def test_default_username(self) -> None:
        msg = ThreadMessage(user_id="U1", text="test", ts="0")
        assert msg.username == "unknown"


class TestNormalizedThread:
    def _make_thread(self, n_messages: int = 3) -> NormalizedThread:
        msgs = [
            ThreadMessage(
                user_id=f"U{i}",
                username=f"user{i}",
                text=f"Message {i}",
                ts=f"{1715000000 + i}.000100",
            )
            for i in range(n_messages)
        ]
        return NormalizedThread(
            channel_id="C001",
            thread_ts="1715000000.000100",
            messages=msgs,
        )

    def test_plain_text(self) -> None:
        thread = self._make_thread(2)
        text = thread.plain_text
        assert "[user0] Message 0" in text
        assert "[user1] Message 1" in text

    def test_message_count(self) -> None:
        thread = self._make_thread(5)
        assert thread.message_count == 5

    def test_empty_thread(self) -> None:
        thread = NormalizedThread(channel_id="C001", thread_ts="0")
        assert thread.plain_text == ""
        assert thread.message_count == 0


class TestFilingIssueDraft:
    def test_defaults(self) -> None:
        draft = FilingIssueDraft(summary="Test", description="Desc")
        assert draft.issue_type == IssueType.TASK
        assert draft.priority == IssuePriority.MEDIUM
        assert draft.labels == []
        assert draft.parent_key is None
        assert draft.assignee_hint is None

    def test_full_construction(self) -> None:
        draft = FilingIssueDraft(
            summary="Q1 CA filing",
            description="File quarterly return for California",
            issue_type=IssueType.STORY,
            priority=IssuePriority.HIGH,
            labels=["q1-filing", "state-ca"],
            parent_key="FILING-100",
            assignee_hint="alice",
        )
        assert draft.summary == "Q1 CA filing"
        assert draft.issue_type == IssueType.STORY
        assert draft.priority == IssuePriority.HIGH
        assert len(draft.labels) == 2
        assert draft.parent_key == "FILING-100"

    def test_summary_max_length(self) -> None:
        with pytest.raises(Exception):
            FilingIssueDraft(summary="x" * 256, description="d")

    def test_enum_values(self) -> None:
        assert IssuePriority.HIGHEST.value == "Highest"
        assert IssueType.BUG.value == "Bug"

    def test_json_roundtrip(self) -> None:
        draft = FilingIssueDraft(
            summary="Test roundtrip",
            description="body",
            labels=["tax"],
        )
        data = draft.model_dump()
        restored = FilingIssueDraft.model_validate(data)
        assert restored == draft
