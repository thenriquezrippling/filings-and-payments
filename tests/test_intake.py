"""Tests for IntakeService: end-to-end pipeline with mocked LLM."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    FilingPeriod,
    FilingYear,
    Impact,
    IssueType,
    LLMExtraction,
    SLAPriority,
    SLATracker,
    ThreadMessage,
)
from tax_ops_filing_bot.services.intake import IntakeService, _sanitize_description


class FakeLLMClient:
    """Returns a fixed LLMExtraction regardless of input."""

    def __init__(self, extraction: LLMExtraction) -> None:
        self._extraction = extraction
        self.last_messages: list | None = None
        self.last_system: str | None = None

    def complete_json(self, messages, response_model, *, system=None):
        self.last_messages = messages
        self.last_system = system
        return self._extraction


PITTSBURGH_EXTRACTION = LLMExtraction(
    summary=(
        "PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE: Tax year displaying "
        "ET-2025 instead of ET-2026 and PEO name defaulting to Rippling PEO 1, Inc."
    ),
    description=(
        "During review of Pittsburgh EIT $0 filing returns, two issues were "
        "identified:\n\n"
        "1. Tax year mismatch: The tax year at the top of the return displays "
        "\"ET-2025\" but should read \"ET-2026\" for the 1Q2026 filing period.\n\n"
        "2. PEO company name on Payroll Expense Tax Allocation Schedule: "
        "All clients are showing \"Rippling PEO 1, Inc.\" as the Company Name "
        "of Professional Employer Organization."
    ),
    confidence=0.92,
    jurisdiction="City of Pittsburgh",
    state="PA",
    tax_type="EIT",
    tax_period="1Q2026",
    agency="PA Local Treasurer - City of Pittsburgh",
    filing_code="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE",
    client_or_entity="Rippling PEO 1, Inc.",
    reporter="Tony",
    impact_scope="all clients",
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
    """End-to-end: Pittsburgh EIT Q1 2026 blocker."""

    def _create_draft(self, extra_messages=None) -> FilingIssueDraft:
        messages = list(PITTSBURGH_THREAD)
        if extra_messages:
            messages.extend(extra_messages)
        fake_llm = FakeLLMClient(PITTSBURGH_EXTRACTION)
        service = IntakeService(fake_llm)
        return service.create_draft(messages, channel="personal-ai-testing")

    def test_issue_type_is_blocker(self) -> None:
        assert self._create_draft().issue_type == IssueType.BLOCKER

    def test_filing_period_q1(self) -> None:
        assert self._create_draft().filing_period == FilingPeriod.Q1

    def test_year_2026(self) -> None:
        assert self._create_draft().year == FilingYear.Y2026

    def test_impact_all_clients(self) -> None:
        assert self._create_draft().impact == Impact.ALL_CLIENTS

    def test_sla_priority_p0(self) -> None:
        assert self._create_draft().sla_priority == SLAPriority.P0_CRITICAL

    def test_sla_tracker_same_day(self) -> None:
        assert self._create_draft().sla_tracker == SLATracker.SAME_DAY

    def test_label_q126_filing_blocker(self) -> None:
        draft = self._create_draft()
        assert "Q126-filing-blocker" in draft.labels

    def test_state_pa(self) -> None:
        assert self._create_draft().state == "PA"

    def test_confidence(self) -> None:
        assert self._create_draft().confidence == 0.92

    def test_source_channel(self) -> None:
        assert self._create_draft().source_channel == "personal-ai-testing"

    def test_reporter(self) -> None:
        assert self._create_draft().reporter == "Tony"

    def test_needs_mapping_review_false(self) -> None:
        assert self._create_draft().needs_mapping_review is False

    def test_filing_unit_code(self) -> None:
        assert self._create_draft().filing_unit_code == \
            "PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE"


class TestDescriptionSanitization:
    """Implementation notes never appear in Jira descriptions."""

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
        description = f"Tax year shows ET-2025.\n{bad_line}\nNeeds correction."
        sanitized = _sanitize_description(description)
        assert bad_line not in sanitized
        assert "Tax year shows ET-2025." in sanitized

    def test_clean_description_unchanged(self) -> None:
        description = (
            "Tax year shows ET-2025 instead of ET-2026.\n"
            "PEO company name is Rippling PEO 1, Inc."
        )
        assert _sanitize_description(description) == description


class TestBotMessageFiltering:
    """Bot-generated messages are excluded from the source transcript."""

    def test_bot_messages_filtered_before_llm(self) -> None:
        bot_messages = [
            ThreadMessage(
                author="Claude", timestamp="3",
                text="I implemented Phase 2. All tests pass.", is_bot=True,
            ),
            ThreadMessage(
                author="Cursor", timestamp="4",
                text="Here's what I implemented in the PR.",
            ),
        ]
        messages = list(PITTSBURGH_THREAD) + bot_messages
        fake_llm = FakeLLMClient(PITTSBURGH_EXTRACTION)
        service = IntakeService(fake_llm)
        service.create_draft(messages, channel="test")

        thread_text = fake_llm.last_messages[0]["content"]
        assert "I implemented" not in thread_text
        assert "Tony" in thread_text
