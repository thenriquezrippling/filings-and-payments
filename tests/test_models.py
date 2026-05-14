"""Tests for FilingIssueDraft, LLMExtraction, and related models."""

from __future__ import annotations

import json

import pytest

from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
    LLMExtraction,
    ThreadMessage,
)


class TestThreadMessage:
    def test_create(self) -> None:
        msg = ThreadMessage(author="Alice", timestamp="2026-01-01T00:00:00", text="hello")
        assert msg.author == "Alice"
        assert msg.text == "hello"
        assert msg.is_bot is False

    def test_from_dict(self) -> None:
        data = {"author": "Bob", "timestamp": "2026-01-01", "text": "test"}
        msg = ThreadMessage.model_validate(data)
        assert msg.author == "Bob"

    def test_bot_flag(self) -> None:
        msg = ThreadMessage(author="bot", timestamp="now", text="hi", is_bot=True)
        assert msg.is_bot is True


class TestIssueType:
    def test_blocker(self) -> None:
        assert IssueType.BLOCKER.value == "Blocker"

    def test_filing_exception(self) -> None:
        assert IssueType.FILING_EXCEPTION.value == "Filing Exception"

    def test_incident(self) -> None:
        assert IssueType.INCIDENT.value == "Incident"

    def test_feature_request(self) -> None:
        assert IssueType.FEATURE_REQUEST.value == "Feature Request"

    def test_process_improvement(self) -> None:
        assert IssueType.PROCESS_IMPROVEMENT.value == "Process Improvement"

    def test_no_bug_type(self) -> None:
        values = {t.value for t in IssueType}
        assert "Bug" not in values

    def test_no_task_type(self) -> None:
        values = {t.value for t in IssueType}
        assert "Task" not in values

    def test_no_story_type(self) -> None:
        values = {t.value for t in IssueType}
        assert "Story" not in values


class TestLLMExtraction:
    def test_minimal(self) -> None:
        ext = LLMExtraction(summary="Test", description="Desc")
        assert ext.confidence == 0.0
        assert ext.jurisdiction is None

    def test_full(self) -> None:
        ext = LLMExtraction(
            summary="Pittsburgh EIT",
            description="Tax year mismatch",
            confidence=0.9,
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period="1Q2026",
            agency="PA Local Treasurer",
            filing_code="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE",
            client_or_entity="Rippling PEO 1, Inc.",
            reporter="Tony",
        )
        assert ext.tax_type == "EIT"
        assert ext.filing_code is not None


class TestFilingIssueDraft:
    def test_minimal_draft(self) -> None:
        draft = FilingIssueDraft(
            summary="Test issue",
            description="Some description",
        )
        assert draft.issue_type == IssueType.BLOCKER
        assert draft.priority == IssuePriority.MEDIUM
        assert draft.labels == []
        assert draft.jurisdiction is None
        assert draft.needs_mapping_review is False
        assert draft.parent_epic_key is None

    def test_full_draft(self) -> None:
        draft = FilingIssueDraft(
            summary="Pittsburgh EIT issue",
            description="Tax year mismatch",
            issue_type=IssueType.BLOCKER,
            priority=IssuePriority.HIGHEST,
            labels=["pittsburgh", "pa-local", "eit", "filing-blocker"],
            parent_epic_key="FILING-101",
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period="1Q2026",
            needs_mapping_review=False,
            confidence=0.9,
        )
        assert draft.issue_type == IssueType.BLOCKER
        assert draft.priority == IssuePriority.HIGHEST
        assert "pittsburgh" in draft.labels
        assert draft.parent_epic_key == "FILING-101"
        assert draft.needs_mapping_review is False

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

    def test_needs_mapping_review_field(self) -> None:
        draft = FilingIssueDraft(
            summary="Unknown agency issue",
            description="Desc",
            needs_mapping_review=True,
        )
        assert draft.needs_mapping_review is True
        assert draft.parent_epic_key is None
