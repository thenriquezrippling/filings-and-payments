"""Tests for IntakeService: end-to-end pipeline with mocked LLM (requirements F.1-F.6)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
    LLMExtraction,
    ThreadMessage,
)
from tax_ops_filing_bot.services.intake import IntakeService, _sanitize_description


class FakeLLMClient:
    """Returns a fixed LLMExtraction regardless of input."""

    def __init__(self, extraction: LLMExtraction) -> None:
        self._extraction = extraction
        self.last_messages: list | None = None
        self.last_system: str | None = None
        self.call_count: int = 0

    def complete_json(self, messages, response_model, *, system=None):
        self.last_messages = messages
        self.last_system = system
        self.call_count += 1
        return self._extraction


PITTSBURGH_EIT_EXTRACTION = LLMExtraction(
    summary=(
        "Pittsburgh EIT 1Q2026: Tax year displaying ET-2025 instead of "
        "ET-2026 and PEO name defaulting to Rippling PEO 1, Inc."
    ),
    description=(
        "During review of Pittsburgh EIT returns showing $0 balances "
        "(PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE 1Q2026), two issues "
        "were identified:\n\n"
        "1. Tax year mismatch: The tax year at the top of the return "
        "displays \"ET-2025\" but should read \"ET-2026\" for the "
        "1Q2026 filing period.\n\n"
        "2. PEO company name on Payroll Expense Tax Allocation Schedule: "
        "All clients are showing \"Rippling PEO 1, Inc.\" as the Company "
        "Name of Professional Employer Organization."
    ),
    confidence=0.92,
    jurisdiction="City of Pittsburgh",
    tax_type="EIT",
    tax_period="1Q2026",
    agency="PA Local Treasurer - City of Pittsburgh",
    filing_code="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE",
    client_or_entity="Rippling PEO 1, Inc.",
    reporter="Tony",
)

PITTSBURGH_THREAD = [
    ThreadMessage(
        author="Tony",
        timestamp="5/14/2026, 6:37:57 AM",
        text="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE 1Q2026",
    ),
    ThreadMessage(
        author="Tony",
        timestamp="5/14/2026, 6:38:17 AM",
        text=(
            "I am reviewing Pittsburgh EIT 0's and I wanted clarification on:\n\n"
            "-The tax year at the top of the return is showing \"ET-2025\" "
            "(This may need to be changed to 2026)\n"
            "-The Payroll Expense Tax Allocation Schedule Form is also on the "
            "second page, can we confirm if this needs to be included and if so, "
            "all the client's are showing Rippling PEO 1, Inc. as Company Name "
            "of Professional Employer Organization."
        ),
    ),
]


class TestPittsburghEITDraft:
    """End-to-end tests for the Pittsburgh EIT thread."""

    def _create_draft(self, extra_messages: list[ThreadMessage] | None = None) -> FilingIssueDraft:
        messages = list(PITTSBURGH_THREAD)
        if extra_messages:
            messages.extend(extra_messages)
        fake_llm = FakeLLMClient(PITTSBURGH_EIT_EXTRACTION)
        service = IntakeService(fake_llm)
        return service.create_draft(messages, channel="personal-ai-testing")

    def test_issue_type_is_blocker(self) -> None:
        """F.2: Pittsburgh EIT classified as Blocker."""
        draft = self._create_draft()
        assert draft.issue_type == IssueType.BLOCKER

    def test_priority_is_highest(self) -> None:
        draft = self._create_draft()
        assert draft.priority == IssuePriority.HIGHEST

    def test_parent_epic_from_mapping(self) -> None:
        """F.3: Parent epic selected from mapping layer."""
        draft = self._create_draft()
        assert draft.parent_epic_key == "FILING-101"

    def test_labels_from_deterministic_rules(self) -> None:
        """F.4: Labels generated from deterministic rules."""
        draft = self._create_draft()
        assert "pittsburgh" in draft.labels
        assert "pa-local" in draft.labels
        assert "eit" in draft.labels
        assert "q1-2026" in draft.labels
        assert "filing-blocker" in draft.labels
        assert "form-output" in draft.labels
        assert "payroll-expense-tax" in draft.labels

    def test_needs_mapping_review_false(self) -> None:
        draft = self._create_draft()
        assert draft.needs_mapping_review is False

    def test_confidence_passed_through(self) -> None:
        draft = self._create_draft()
        assert draft.confidence == 0.92

    def test_source_channel_set(self) -> None:
        draft = self._create_draft()
        assert draft.source_channel == "personal-ai-testing"

    def test_reporter_set(self) -> None:
        draft = self._create_draft()
        assert draft.reporter == "Tony"


class TestDescriptionSanitization:
    """F.1: Implementation notes never appear in Jira descriptions."""

    @pytest.mark.parametrize("bad_line", [
        "I implemented Phase 2 of the bot.",
        "All tests pass and lint is clean.",
        "commit abc123 pushed to main",
        "PR #42 is ready for review",
        "Phase 3 scaffolding complete",
        "All done with the changes",
        "Here's what I implemented:",
        "ruff check passed",
        "pytest -v ran clean",
        "pip install -e completed",
        "git push origin main",
        "Cursor generated this",
        "Claude wrote the code",
    ])
    def test_implementation_notes_removed(self, bad_line: str) -> None:
        """F.1: Each type of implementation note is stripped from descriptions."""
        description = f"Tax year shows ET-2025.\n{bad_line}\nNeeds correction."
        sanitized = _sanitize_description(description)
        assert bad_line not in sanitized
        assert "Tax year shows ET-2025." in sanitized
        assert "Needs correction." in sanitized

    def test_clean_description_unchanged(self) -> None:
        description = (
            "Tax year shows ET-2025 instead of ET-2026.\n"
            "PEO company name is Rippling PEO 1, Inc."
        )
        sanitized = _sanitize_description(description)
        assert sanitized == description

    def test_multiple_bad_lines_all_removed(self) -> None:
        description = (
            "Real issue here.\n"
            "I implemented the fix.\n"
            "All tests pass.\n"
            "lint is clean.\n"
            "Also a real concern."
        )
        sanitized = _sanitize_description(description)
        assert "implemented" not in sanitized
        assert "tests pass" not in sanitized
        assert "lint is clean" not in sanitized
        assert "Real issue here." in sanitized
        assert "Also a real concern." in sanitized


class TestBotMessageFiltering:
    """F.6: Bot-generated messages are excluded from the source transcript."""

    def test_bot_messages_filtered_before_llm(self) -> None:
        bot_messages = [
            ThreadMessage(
                author="Claude",
                timestamp="3",
                text="I implemented Phase 2. All tests pass.",
                is_bot=True,
            ),
            ThreadMessage(
                author="Cursor",
                timestamp="4",
                text="Here's what I implemented in the PR.",
            ),
        ]
        messages = list(PITTSBURGH_THREAD) + bot_messages
        fake_llm = FakeLLMClient(PITTSBURGH_EIT_EXTRACTION)
        service = IntakeService(fake_llm)
        service.create_draft(messages, channel="test")

        thread_text = fake_llm.last_messages[0]["content"]
        assert "I implemented" not in thread_text
        assert "tests pass" not in thread_text
        assert "Tony" in thread_text

    def test_dev_chatter_filtered(self) -> None:
        dev_messages = [
            ThreadMessage(
                author="DevPerson",
                timestamp="5",
                text="All tests pass, lint is clean, commit pushed.",
            ),
        ]
        messages = list(PITTSBURGH_THREAD) + dev_messages
        fake_llm = FakeLLMClient(PITTSBURGH_EIT_EXTRACTION)
        service = IntakeService(fake_llm)
        service.create_draft(messages, channel="test")

        thread_text = fake_llm.last_messages[0]["content"]
        assert "lint is clean" not in thread_text


class TestUnmappedAgency:
    """F.5: Unmapped agencies set needs_mapping_review = true."""

    def test_unknown_agency_sets_review_flag(self) -> None:
        extraction = LLMExtraction(
            summary="Denver OPT filing issue",
            description="Occupational privilege tax amount is incorrect.",
            confidence=0.8,
            jurisdiction="City of Denver",
            tax_type="OPT",
            tax_period="2Q2026",
            agency="Denver Revenue",
        )
        fake_llm = FakeLLMClient(extraction)
        service = IntakeService(fake_llm)
        messages = [
            ThreadMessage(author="Jane", timestamp="1", text="Denver OPT issue"),
        ]
        draft = service.create_draft(messages, channel="test")
        assert draft.needs_mapping_review is True
        assert draft.parent_epic_key is None

    def test_unknown_agency_no_invented_epic(self) -> None:
        extraction = LLMExtraction(
            summary="Unknown filing issue",
            description="Something is wrong.",
            confidence=0.5,
        )
        fake_llm = FakeLLMClient(extraction)
        service = IntakeService(fake_llm)
        messages = [
            ThreadMessage(author="User", timestamp="1", text="Help"),
        ]
        draft = service.create_draft(messages, channel="test")
        assert draft.parent_epic_key is None
        assert draft.needs_mapping_review is True


class TestIntakeServiceFormatThread:
    def test_format_thread(self) -> None:
        text = IntakeService.format_thread(PITTSBURGH_THREAD)
        assert "Tony" in text
        assert "PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE" in text
        assert "ET-2025" in text
