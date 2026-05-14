"""Tests for IntakeService with mocked LLM."""

from __future__ import annotations

from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
    ThreadMessage,
)
from tax_ops_filing_bot.services.intake import IntakeService


class FakeLLMClient:
    """Returns a fixed FilingIssueDraft regardless of input."""

    def __init__(self, draft: FilingIssueDraft) -> None:
        self._draft = draft
        self.last_messages = None
        self.last_system = None

    def complete_json(self, messages, response_model, *, system=None):
        self.last_messages = messages
        self.last_system = system
        return self._draft


SAMPLE_MESSAGES = [
    ThreadMessage(author="Tony", timestamp="2026-05-14T06:37:57", text="PITTSBURGH EIT 1Q2026"),
    ThreadMessage(
        author="Tony",
        timestamp="2026-05-14T06:38:17",
        text="Tax year showing ET-2025, should be 2026",
    ),
]


class TestIntakeService:
    def test_format_thread(self) -> None:
        text = IntakeService.format_thread(SAMPLE_MESSAGES)
        assert "Tony" in text
        assert "PITTSBURGH EIT 1Q2026" in text
        assert "ET-2025" in text

    def test_create_draft_calls_llm(self) -> None:
        expected_draft = FilingIssueDraft(
            summary="Pittsburgh EIT 1Q2026 tax year issue",
            description="Tax year mismatch on return",
            issue_type=IssueType.BUG,
            priority=IssuePriority.HIGH,
        )
        fake_llm = FakeLLMClient(expected_draft)
        service = IntakeService(fake_llm)

        draft = service.create_draft(SAMPLE_MESSAGES, channel="test-channel")

        assert draft.summary == "Pittsburgh EIT 1Q2026 tax year issue"
        assert draft.issue_type == IssueType.BUG
        assert draft.source_channel == "test-channel"
        assert fake_llm.last_messages is not None
        assert fake_llm.last_system is not None

    def test_create_draft_preserves_source_channel_from_llm(self) -> None:
        draft_with_channel = FilingIssueDraft(
            summary="Test",
            description="Desc",
            source_channel="llm-inferred-channel",
        )
        fake_llm = FakeLLMClient(draft_with_channel)
        service = IntakeService(fake_llm)

        draft = service.create_draft(SAMPLE_MESSAGES, channel="caller-channel")
        assert draft.source_channel == "llm-inferred-channel"
