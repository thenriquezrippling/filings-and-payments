"""Tests for FilingIssueDraft and related models."""

from __future__ import annotations

import json

import pytest

from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
    ThreadMessage,
)


class TestThreadMessage:
    def test_create(self) -> None:
        msg = ThreadMessage(author="Alice", timestamp="2026-01-01T00:00:00", text="hello")
        assert msg.author == "Alice"
        assert msg.text == "hello"

    def test_from_dict(self) -> None:
        data = {"author": "Bob", "timestamp": "2026-01-01", "text": "test"}
        msg = ThreadMessage.model_validate(data)
        assert msg.author == "Bob"


class TestFilingIssueDraft:
    def test_minimal_draft(self) -> None:
        draft = FilingIssueDraft(
            summary="Test issue",
            description="Some description",
        )
        assert draft.issue_type == IssueType.TASK
        assert draft.priority == IssuePriority.MEDIUM
        assert draft.labels == []
        assert draft.jurisdiction is None

    def test_full_draft(self) -> None:
        draft = FilingIssueDraft(
            summary="Pittsburgh EIT issue",
            description="Tax year mismatch",
            issue_type=IssueType.BUG,
            priority=IssuePriority.HIGH,
            labels=["pittsburgh", "EIT"],
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period="1Q2026",
            client_or_entity="Rippling PEO 1, Inc.",
            source_channel="personal-ai-testing",
            reporter="Tony",
        )
        assert draft.issue_type == IssueType.BUG
        assert draft.priority == IssuePriority.HIGH
        assert "pittsburgh" in draft.labels
        assert draft.jurisdiction == "City of Pittsburgh"

    def test_roundtrip_json(self) -> None:
        draft = FilingIssueDraft(
            summary="Test",
            description="Desc",
            labels=["a", "b"],
        )
        data = json.loads(draft.model_dump_json())
        restored = FilingIssueDraft.model_validate(data)
        assert restored.summary == "Test"
        assert restored.labels == ["a", "b"]

    def test_summary_max_length(self) -> None:
        with pytest.raises(Exception):
            FilingIssueDraft(
                summary="x" * 256,
                description="too long summary",
            )
