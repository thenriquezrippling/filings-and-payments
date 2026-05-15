"""Tests for the deterministic mapping layer — based on real FILING project data."""

from __future__ import annotations

from datetime import date

from tax_ops_filing_bot.models.filing import (
    FilingFrequency,
    FilingPeriod,
    FilingYear,
    Impact,
    IssueType,
    SLAPriority,
    SLATracker,
)
from tax_ops_filing_bot.services.mapping import (
    apply_mapping,
    build_blocker_label,
    build_retro_label,
    classify_issue_type,
    escalate_sla_for_due_date,
    infer_filing_frequency,
    infer_impact,
    parse_period,
    parse_period_meta,
)


class TestParsePeriod:
    def test_1q2026(self) -> None:
        assert parse_period("1Q2026") == (1, 2026)

    def test_q1_2026(self) -> None:
        assert parse_period("Q1 2026") == (1, 2026)

    def test_q2_2026(self) -> None:
        assert parse_period("Q2 2026") == (2, 2026)

    def test_bare_year(self) -> None:
        assert parse_period("2026") == (None, 2026)

    def test_none(self) -> None:
        assert parse_period(None) == (None, None)

    def test_april_2026_maps_to_q2(self) -> None:
        assert parse_period("April 2026") == (2, 2026)


class TestParsePeriodMeta:
    def test_explicit_quarter(self) -> None:
        assert parse_period_meta("Q1 2026") == (1, 2026, True)

    def test_month_text_not_explicit_quarter(self) -> None:
        assert parse_period_meta("April 2026") == (2, 2026, False)


class TestInferFilingFrequency:
    def test_explicit_quarter(self) -> None:
        assert infer_filing_frequency(1, True) == FilingFrequency.QUARTERLY

    def test_month_derived_quarter(self) -> None:
        assert infer_filing_frequency(2, False) == FilingFrequency.MONTHLY


class TestDueDateSlaEscalation:
    def test_escalates_within_three_days(self) -> None:
        assert escalate_sla_for_due_date(
            IssueType.BLOCKER,
            SLAPriority.P3_MEDIUM,
            explicit_due_date=date(2026, 5, 17),
            today=date(2026, 5, 15),
        ) == SLAPriority.P0_CRITICAL

    def test_no_escalation_beyond_window(self) -> None:
        assert escalate_sla_for_due_date(
            IssueType.BLOCKER,
            SLAPriority.P1_URGENT,
            explicit_due_date=date(2026, 5, 25),
            today=date(2026, 5, 15),
        ) == SLAPriority.P1_URGENT


class TestBuildBlockerLabel:
    """Blocker labels follow Q{quarter}{2-digit-year}-filing-blocker convention."""

    def test_q1_2026(self) -> None:
        assert build_blocker_label(1, 2026) == "Q126-filing-blocker"

    def test_q2_2026(self) -> None:
        assert build_blocker_label(2, 2026) == "Q226-filing-blocker"

    def test_q3_2025(self) -> None:
        assert build_blocker_label(3, 2025) == "Q325-filing-blocker"

    def test_q4_2027(self) -> None:
        assert build_blocker_label(4, 2027) == "Q427-filing-blocker"

    def test_none_quarter(self) -> None:
        assert build_blocker_label(None, 2026) is None

    def test_none_year(self) -> None:
        assert build_blocker_label(1, None) is None


class TestBuildRetroLabel:
    def test_q1_2026(self) -> None:
        assert build_retro_label(1, 2026) == "q126-retro-item"

    def test_q2_2026(self) -> None:
        assert build_retro_label(2, 2026) == "q226-retro-item"


class TestClassifyIssueType:
    def test_blocker_tax_year_mismatch(self) -> None:
        assert classify_issue_type(
            "Tax year shows ET-2025 instead of ET-2026"
        ) == IssueType.BLOCKER

    def test_blocker_peo_name(self) -> None:
        assert classify_issue_type(
            "All clients are showing PEO company name incorrectly"
        ) == IssueType.BLOCKER

    def test_blocker_missing_ssn(self) -> None:
        assert classify_issue_type(
            "Missing SSN and invalid employee name"
        ) == IssueType.BLOCKER

    def test_blocker_negative_wages(self) -> None:
        assert classify_issue_type(
            "Negative taxable wages in file"
        ) == IssueType.BLOCKER

    def test_blocker_file_regen(self) -> None:
        assert classify_issue_type(
            "File regeneration issue with $0 filings"
        ) == IssueType.BLOCKER

    def test_filing_exception(self) -> None:
        assert classify_issue_type(
            "Filing exception request for client exclusion"
        ) == IssueType.FILING_EXCEPTION

    def test_feature_request(self) -> None:
        assert classify_issue_type(
            "Enhancement request for a new report format"
        ) == IssueType.FEATURE_REQUEST

    def test_default_is_blocker(self) -> None:
        assert classify_issue_type(
            "Something is wrong with the filing"
        ) == IssueType.BLOCKER


class TestInferImpact:
    def test_all_clients_from_hint(self) -> None:
        assert infer_impact("desc", "all clients") == Impact.ALL_CLIENTS

    def test_multiple_from_hint(self) -> None:
        assert infer_impact("desc", "multiple clients") == Impact.MULTIPLE_CLIENTS

    def test_single_from_hint(self) -> None:
        assert infer_impact("desc", "single client") == Impact.SINGLE_CLIENT

    def test_all_clients_from_description(self) -> None:
        assert infer_impact(
            "All clients are showing Rippling PEO", None
        ) == Impact.ALL_CLIENTS

    def test_none_when_unknown(self) -> None:
        assert infer_impact("some issue", None) is None


class TestApplyMappingPittsburghEIT:
    """Pittsburgh EIT Q1 2026 blocker — matches real FILING-5967."""

    def _get_result(self):
        return apply_mapping(
            description=(
                "Tax year at top of return displays ET-2025 but should read "
                "ET-2026. All clients are showing Rippling PEO 1, Inc. as "
                "Company Name of Professional Employer Organization."
            ),
            tax_period="1Q2026",
            impact_hint="all clients",
        )

    def test_issue_type_is_blocker(self) -> None:
        assert self._get_result().issue_type == IssueType.BLOCKER

    def test_filing_period_q1(self) -> None:
        assert self._get_result().filing_period == FilingPeriod.Q1

    def test_year_2026(self) -> None:
        assert self._get_result().year == FilingYear.Y2026

    def test_filing_frequency_quarterly(self) -> None:
        assert self._get_result().filing_frequency == FilingFrequency.QUARTERLY

    def test_impact_all_clients(self) -> None:
        assert self._get_result().impact == Impact.ALL_CLIENTS

    def test_sla_priority_p0(self) -> None:
        assert self._get_result().sla_priority == SLAPriority.P0_CRITICAL

    def test_sla_tracker_same_day(self) -> None:
        assert self._get_result().sla_tracker == SLATracker.SAME_DAY

    def test_label_q126_filing_blocker(self) -> None:
        result = self._get_result()
        assert "Q126-filing-blocker" in result.labels

    def test_no_needs_mapping_review(self) -> None:
        assert self._get_result().needs_mapping_review is False

    def test_imminent_due_escalates_even_when_impact_unknown(self) -> None:
        result = apply_mapping(
            description="Something is wrong with a filing",
            tax_period="Q1 2026",
            impact_hint=None,
            explicit_due_date=date(2026, 5, 16),
            today=date(2026, 5, 15),
        )
        assert result.sla_priority == SLAPriority.P0_CRITICAL
        assert result.sla_tracker == SLATracker.SAME_DAY


class TestApplyMappingMonthly:
    def test_april_2026_is_monthly_with_q2_period(self) -> None:
        result = apply_mapping(
            description="April 2026 withholding looks wrong",
            tax_period="April 2026",
        )
        assert result.filing_frequency == FilingFrequency.MONTHLY
        assert result.filing_period == FilingPeriod.Q2
        assert result.year == FilingYear.Y2026


class TestApplyMappingQ2:
    """Q2 2026 blocker should produce Q226-filing-blocker label."""

    def test_q2_label(self) -> None:
        result = apply_mapping(
            description="Wage discrepancies in bulk file for Q2",
            tax_period="Q2 2026",
        )
        assert "Q226-filing-blocker" in result.labels

    def test_q2_filing_period(self) -> None:
        result = apply_mapping(
            description="Wage discrepancies in bulk file for Q2",
            tax_period="Q2 2026",
        )
        assert result.filing_period == FilingPeriod.Q2


class TestApplyMappingFilingException:
    def test_issue_type(self) -> None:
        result = apply_mapping(
            description="Filing exception request for client exclusion from Q1",
            tax_period="Q1 2026",
        )
        assert result.issue_type == IssueType.FILING_EXCEPTION

    def test_exclusion_label(self) -> None:
        result = apply_mapping(
            description="Filing exclusion for client from quarterly filings",
            tax_period="Q1 2026",
        )
        assert "q126-exclusions" in result.labels

    def test_no_sla_for_exception(self) -> None:
        result = apply_mapping(
            description="Filing exception after submission, needs amendment",
            tax_period="Q1 2026",
        )
        assert result.sla_priority is None


class TestApplyMappingNoPeriod:
    """Missing period should flag needs_mapping_review."""

    def test_needs_review(self) -> None:
        result = apply_mapping(
            description="Something is wrong with a filing",
            tax_period=None,
        )
        assert result.needs_mapping_review is True

    def test_no_blocker_label(self) -> None:
        result = apply_mapping(
            description="Something is wrong with a filing",
            tax_period=None,
        )
        assert not any("filing-blocker" in lbl for lbl in result.labels)
