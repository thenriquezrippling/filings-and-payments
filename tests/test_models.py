"""Tests for FILING project models — validates enums match live Jira schema."""

from __future__ import annotations

import json

import pytest

from tax_ops_filing_bot.models.filing import (
    FILING_PERIOD_IDS,
    IMPACT_IDS,
    ISSUE_TYPE_JIRA_IDS,
    SLA_PRIORITY_IDS,
    FilingFrequency,
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


class TestIssueType:
    """Issue types must match the real FILING project — no generic software types."""

    def test_blocker_exists(self) -> None:
        assert IssueType.BLOCKER.value == "Blocker"

    def test_filing_exception_exists(self) -> None:
        assert IssueType.FILING_EXCEPTION.value == "Filing Exception"

    def test_feature_request_exists(self) -> None:
        assert IssueType.FEATURE_REQUEST.value == "Feature Request"

    def test_quarterly_exists(self) -> None:
        assert IssueType.QUARTERLY.value == "Quarterly"

    def test_monthly_exists(self) -> None:
        assert IssueType.MONTHLY.value == "Monthly"

    def test_retro_exists(self) -> None:
        assert IssueType.RETRO.value == "Retro"

    def test_no_bug_type(self) -> None:
        assert "Bug" not in {t.value for t in IssueType}

    def test_no_task_type(self) -> None:
        assert "Task" not in {t.value for t in IssueType}

    def test_no_story_type(self) -> None:
        assert "Story" not in {t.value for t in IssueType}

    def test_no_incident_type(self) -> None:
        assert "Incident" not in {t.value for t in IssueType}

    def test_no_process_improvement_type(self) -> None:
        assert "Process Improvement" not in {t.value for t in IssueType}

    def test_all_have_jira_ids(self) -> None:
        for t in IssueType:
            assert t in ISSUE_TYPE_JIRA_IDS, f"{t} missing Jira ID"

    def test_blocker_jira_id(self) -> None:
        assert ISSUE_TYPE_JIRA_IDS[IssueType.BLOCKER] == "20302"


class TestSLAPriority:
    def test_values(self) -> None:
        assert SLAPriority.P0_CRITICAL.value == "P0 - Critical"
        assert SLAPriority.P1_URGENT.value == "P1 - Urgent"
        assert SLAPriority.P2_HIGH.value == "P2 - High"
        assert SLAPriority.P3_MEDIUM.value == "P3 - Medium"
        assert SLAPriority.RETRO.value == "Retro"

    def test_all_have_jira_ids(self) -> None:
        for p in SLAPriority:
            assert p in SLA_PRIORITY_IDS


class TestImpact:
    def test_values(self) -> None:
        assert Impact.ALL_CLIENTS.value == "All Clients"
        assert Impact.MULTIPLE_CLIENTS.value == "Multiple Clients"
        assert Impact.SINGLE_CLIENT.value == "Single Client"

    def test_all_have_jira_ids(self) -> None:
        for i in Impact:
            assert i in IMPACT_IDS


class TestFilingPeriod:
    def test_quarter_values(self) -> None:
        assert FilingPeriod.Q1.value == "Q1"
        assert FilingPeriod.Q2.value == "Q2"
        assert FilingPeriod.Q3.value == "Q3"
        assert FilingPeriod.Q4.value == "Q4"

    def test_all_have_jira_ids(self) -> None:
        for fp in FilingPeriod:
            assert fp in FILING_PERIOD_IDS


class TestThreadMessage:
    def test_create(self) -> None:
        msg = ThreadMessage(author="Alice", timestamp="2026-01-01", text="hello")
        assert msg.author == "Alice"
        assert msg.is_bot is False

    def test_bot_flag(self) -> None:
        msg = ThreadMessage(author="bot", timestamp="now", text="hi", is_bot=True)
        assert msg.is_bot is True


class TestLLMExtraction:
    def test_minimal(self) -> None:
        ext = LLMExtraction(summary="Test", description="Desc")
        assert ext.confidence == 0.0
        assert ext.state is None
        assert ext.impact_scope is None

    def test_full(self) -> None:
        ext = LLMExtraction(
            summary="Pittsburgh EIT",
            description="Tax year mismatch",
            confidence=0.9,
            jurisdiction="City of Pittsburgh",
            state="PA",
            tax_type="EIT",
            tax_period="1Q2026",
            filing_code="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE",
            ff_client_id="12345",
            impact_scope="all clients",
        )
        assert ext.state == "PA"
        assert ext.ff_client_id == "12345"


class TestFilingIssueDraft:
    def test_minimal_draft(self) -> None:
        draft = FilingIssueDraft(summary="Test", description="Desc")
        assert draft.issue_type == IssueType.BLOCKER
        assert draft.labels == []
        assert draft.filing_period is None
        assert draft.sla_priority is None
        assert draft.impact is None
        assert draft.needs_mapping_review is False

    def test_full_blocker_draft(self) -> None:
        draft = FilingIssueDraft(
            summary="Pittsburgh EIT issue",
            description="Tax year mismatch",
            issue_type=IssueType.BLOCKER,
            labels=["Q126-filing-blocker"],
            filing_period=FilingPeriod.Q1,
            year=FilingYear.Y2026,
            sla_priority=SLAPriority.P0_CRITICAL,
            sla_tracker=SLATracker.SAME_DAY,
            filing_frequency=FilingFrequency.QUARTERLY,
            ff_client_id="12345",
            impact=Impact.ALL_CLIENTS,
            state="PA",
        )
        assert draft.sla_priority == SLAPriority.P0_CRITICAL
        assert draft.filing_period == FilingPeriod.Q1
        assert draft.year == FilingYear.Y2026
        assert draft.impact == Impact.ALL_CLIENTS

    def test_roundtrip_json(self) -> None:
        draft = FilingIssueDraft(
            summary="Test",
            description="Desc",
            labels=["Q126-filing-blocker"],
            filing_period=FilingPeriod.Q1,
            year=FilingYear.Y2026,
        )
        data = json.loads(draft.model_dump_json())
        restored = FilingIssueDraft.model_validate(data)
        assert restored.filing_period == FilingPeriod.Q1
        assert restored.labels == ["Q126-filing-blocker"]

    def test_summary_max_length(self) -> None:
        with pytest.raises(Exception):
            FilingIssueDraft(summary="x" * 256, description="too long")
