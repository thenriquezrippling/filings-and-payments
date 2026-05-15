"""Tests for IntakeService: end-to-end pipeline with mocked LLM.

Due date source of truth:
  1. Matched child filing ticket duedate
  2. Validated explicit date from thread text
  3. If neither → blank + needs_mapping_review
"""

from __future__ import annotations

from datetime import date

import pytest

from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    FilingPeriod,
    FilingYear,
    Impact,
    IssueType,
    LLMExtraction,
    SLAPriority,
    SLAStatus,
    SLATracker,
    ThreadMessage,
)
from tax_ops_filing_bot.services.filing_reference import EpicChildIssue
from tax_ops_filing_bot.services.intake import (
    IntakeService,
    _sanitize_description,
    parse_iso_date,
    validate_date_in_thread,
)


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
    due_date=None,
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


class TestParseIsoDate:
    def test_valid(self) -> None:
        assert parse_iso_date("2026-05-15") is not None
        assert parse_iso_date("2026-05-15").isoformat() == "2026-05-15"

    def test_invalid(self) -> None:
        assert parse_iso_date("not-a-date") is None

    def test_none(self) -> None:
        assert parse_iso_date(None) is None

    def test_empty(self) -> None:
        assert parse_iso_date("") is None


class TestValidateDateInThread:
    def test_iso_format_found(self) -> None:
        assert validate_date_in_thread(date(2026, 4, 30), "Due by 2026-04-30") is True

    def test_slash_format_found(self) -> None:
        assert validate_date_in_thread(date(2026, 4, 30), "Due by 4/30/2026") is True

    def test_slash_short_year(self) -> None:
        assert validate_date_in_thread(date(2026, 4, 30), "Due by 4/30/26") is True

    def test_month_day_no_year(self) -> None:
        assert validate_date_in_thread(date(2026, 4, 30), "Due by 4/30") is True

    def test_month_name_found(self) -> None:
        assert validate_date_in_thread(date(2026, 4, 30), "Due by April 30") is True

    def test_hallucinated_date_not_found(self) -> None:
        assert validate_date_in_thread(
            date(2026, 4, 30),
            "No dates mentioned in this thread at all"
        ) is False

    def test_wrong_date_not_found(self) -> None:
        assert validate_date_in_thread(
            date(2026, 4, 30),
            "This thread mentions 5/15 but no other dates"
        ) is False


class TestDueDateSourceOfTruth:
    """Due date priority: child ticket > validated thread date > blank."""

    def test_child_ticket_duedate_is_primary(self) -> None:
        """Child filing ticket's due date takes priority."""
        children = [
            EpicChildIssue(
                key="FILING-5001",
                summary=(
                    "Pennsylvania Q1 2026 Quarterly Local — "
                    "PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE"
                ),
                issue_type_name="Quarterly",
                duedate="2026-04-30",
            ),
        ]
        fake_llm = FakeLLMClient(PITTSBURGH_EXTRACTION)
        service = IntakeService(fake_llm)
        draft = service.create_draft(
            PITTSBURGH_THREAD,
            channel="test",
            epic_child_issues=children,
            today=date(2026, 4, 27),
        )
        assert draft.due_date == "2026-04-30"
        assert draft.related_filing_issue_keys == ["FILING-5001"]

    def test_validated_thread_date_fallback(self) -> None:
        """Thread date used only when child ticket doesn't provide one."""
        extraction = PITTSBURGH_EXTRACTION.model_copy(
            update={"due_date": "2026-04-30"}
        )
        thread = list(PITTSBURGH_THREAD) + [
            ThreadMessage(author="Tony", timestamp="later", text="Due date is 4/30/2026"),
        ]
        fake_llm = FakeLLMClient(extraction)
        service = IntakeService(fake_llm)
        draft = service.create_draft(thread, channel="test", today=date(2026, 4, 20))
        assert draft.due_date == "2026-04-30"

    def test_hallucinated_date_rejected(self) -> None:
        """LLM-inferred date not found in thread → rejected."""
        extraction = PITTSBURGH_EXTRACTION.model_copy(
            update={"due_date": "2026-04-30"}
        )
        fake_llm = FakeLLMClient(extraction)
        service = IntakeService(fake_llm)
        draft = service.create_draft(
            PITTSBURGH_THREAD,
            channel="test",
            today=date(2026, 4, 20),
        )
        assert draft.due_date is None
        assert draft.needs_mapping_review is True

    def test_no_date_anywhere_leaves_blank(self) -> None:
        fake_llm = FakeLLMClient(PITTSBURGH_EXTRACTION)
        service = IntakeService(fake_llm)
        draft = service.create_draft(
            PITTSBURGH_THREAD, channel="test", today=date(2026, 4, 20),
        )
        assert draft.due_date is None
        assert draft.needs_mapping_review is True


class TestSLAFromChildTicketDueDate:
    """When due date comes from child ticket, SLA should be recomputed."""

    def test_child_due_date_triggers_sla(self) -> None:
        children = [
            EpicChildIssue(
                key="FILING-5001",
                summary=(
                    "Pennsylvania Q1 2026 Quarterly Local — "
                    "PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE"
                ),
                issue_type_name="Quarterly",
                duedate="2026-04-30",
            ),
        ]
        fake_llm = FakeLLMClient(PITTSBURGH_EXTRACTION)
        service = IntakeService(fake_llm)
        draft = service.create_draft(
            PITTSBURGH_THREAD,
            channel="test",
            epic_child_issues=children,
            today=date(2026, 4, 27),
        )
        assert draft.sla_priority == SLAPriority.P0_CRITICAL
        assert draft.sla_tracker == SLATracker.SAME_DAY
        assert draft.sla_status == SLAStatus.AT_RISK


class TestPittsburghEITDraft:
    """End-to-end: Pittsburgh EIT Q1 2026 blocker."""

    def _create_draft(self) -> FilingIssueDraft:
        fake_llm = FakeLLMClient(PITTSBURGH_EXTRACTION)
        service = IntakeService(fake_llm)
        return service.create_draft(
            PITTSBURGH_THREAD, channel="personal-ai-testing",
            today=date(2026, 4, 20),
        )

    def test_issue_type_is_blocker(self) -> None:
        assert self._create_draft().issue_type == IssueType.BLOCKER

    def test_filing_period_q1(self) -> None:
        assert self._create_draft().filing_period == FilingPeriod.Q1

    def test_year_2026(self) -> None:
        assert self._create_draft().year == FilingYear.Y2026

    def test_state_pa(self) -> None:
        assert self._create_draft().state == "PA"

    def test_confidence(self) -> None:
        assert self._create_draft().confidence == 0.92

    def test_no_default_priority_field(self) -> None:
        """Jira default Priority is NOT populated."""
        draft = self._create_draft()
        assert not hasattr(draft, "priority")

    def test_label_q126_filing_blocker(self) -> None:
        assert "Q126-filing-blocker" in self._create_draft().labels


class TestDescriptionSanitization:
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
