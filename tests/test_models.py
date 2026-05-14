"""Tests for Pydantic models (Phase 2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tax_ops_filing_bot.models import (
    AgencyCode,
    FilingIssueDraft,
    FilingIssueCategory,
    SyncRequest,
    ThreadContext,
    ThreadMessage,
)


class TestThreadMessage:
    def test_basic(self) -> None:
        m = ThreadMessage(user="U123", text="hello", ts="1234567890.000001")
        assert m.user == "U123"
        assert m.text == "hello"
        assert m.ts == "1234567890.000001"


class TestThreadContext:
    def _make_ctx(self, n_messages: int = 3) -> ThreadContext:
        messages = [
            ThreadMessage(user=f"U{i}", text=f"msg {i}", ts=f"100{i}.000000")
            for i in range(n_messages)
        ]
        return ThreadContext(
            channel_id="C123",
            thread_ts="1000.000000",
            messages=messages,
        )

    def test_reply_count(self) -> None:
        ctx = self._make_ctx(5)
        assert ctx.reply_count == 4

    def test_minimum_one_message(self) -> None:
        with pytest.raises(ValidationError):
            ThreadContext(channel_id="C1", thread_ts="1.0", messages=[])

    def test_permalink_optional(self) -> None:
        ctx = self._make_ctx()
        assert ctx.permalink is None
        ctx2 = ThreadContext(
            channel_id="C1",
            thread_ts="1.0",
            messages=[ThreadMessage(user="U1", text="hi", ts="1.0")],
            permalink="https://slack.com/link",
        )
        assert ctx2.permalink == "https://slack.com/link"


class TestFilingIssueDraft:
    def test_valid_draft(self) -> None:
        draft = FilingIssueDraft(
            summary="FLSUI missing SSNs for Q1 2026",
            description="Files generated with blank SSNs...",
            category=FilingIssueCategory.MISSING_EMPLOYEE_DATA,
            agency=AgencyCode.FLSUI,
            priority="P1",
            labels=["q1-2026"],
            affected_entity_ids=["FFID-123"],
            suggested_dri="haris",
            confidence=0.85,
        )
        assert draft.summary == "FLSUI missing SSNs for Q1 2026"
        assert draft.category == FilingIssueCategory.MISSING_EMPLOYEE_DATA
        assert draft.agency == AgencyCode.FLSUI

    def test_defaults(self) -> None:
        draft = FilingIssueDraft(
            summary="Test",
            description="desc",
            category=FilingIssueCategory.OTHER,
            confidence=0.5,
        )
        assert draft.priority == "P1"
        assert draft.labels == []
        assert draft.agency is None
        assert draft.suggested_dri is None

    def test_invalid_priority(self) -> None:
        with pytest.raises(ValidationError):
            FilingIssueDraft(
                summary="Test",
                description="desc",
                category=FilingIssueCategory.OTHER,
                priority="HIGH",
                confidence=0.5,
            )

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FilingIssueDraft(
                summary="Test",
                description="desc",
                category=FilingIssueCategory.OTHER,
                confidence=1.5,
            )

    def test_summary_max_length(self) -> None:
        with pytest.raises(ValidationError):
            FilingIssueDraft(
                summary="x" * 256,
                description="desc",
                category=FilingIssueCategory.OTHER,
                confidence=0.5,
            )

    def test_all_categories(self) -> None:
        for cat in FilingIssueCategory:
            draft = FilingIssueDraft(
                summary="test",
                description="desc",
                category=cat,
                confidence=0.5,
            )
            assert draft.category == cat


class TestSyncRequest:
    def test_valid_sync(self) -> None:
        req = SyncRequest(
            issue_key="FILING-5911",
            thread=ThreadContext(
                channel_id="C1",
                thread_ts="1.0",
                messages=[ThreadMessage(user="U1", text="hi", ts="1.0")],
            ),
        )
        assert req.issue_key == "FILING-5911"
        assert req.append_only is True

    def test_invalid_issue_key(self) -> None:
        with pytest.raises(ValidationError):
            SyncRequest(
                issue_key="not-valid",
                thread=ThreadContext(
                    channel_id="C1",
                    thread_ts="1.0",
                    messages=[ThreadMessage(user="U1", text="hi", ts="1.0")],
                ),
            )
