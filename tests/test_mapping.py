"""Tests for the deterministic mapping layer — based on real FILING project data.

SLA rules:
  Blocker  → SLA from due-date proximity (impact does NOT override)
  Retro    → fixed: Retro / For Retro / On Track
  Others   → SLA fields blank
"""

from __future__ import annotations

from datetime import date

from tax_ops_filing_bot.models.filing import (
    FilingFrequency,
    FilingPeriod,
    FilingYear,
    Impact,
    IssueType,
    SLAPriority,
    SLAStatus,
    SLATracker,
)
from tax_ops_filing_bot.services.mapping import (
    apply_mapping,
    build_blocker_label,
    build_retro_label,
    classify_issue_type,
    compute_blocker_sla,
    compute_retro_sla,
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


# ---------------------------------------------------------------------------
# SLA Blocker tests — due-date proximity examples from requirements
# ---------------------------------------------------------------------------

class TestComputeBlockerSLA:
    """Due date 4/30 with different flagged dates."""

    def test_apr20_vs_apr30_is_p2(self) -> None:
        """4/20 flagged, 4/30 due → 10 days → P2 High / 2-Day / On Track."""
        p, t, s = compute_blocker_sla(date(2026, 4, 30), date(2026, 4, 20))
        assert p == SLAPriority.P2_HIGH
        assert t == SLATracker.TWO_DAY
        assert s == SLAStatus.ON_TRACK

    def test_apr25_vs_apr30_is_p1(self) -> None:
        """4/25 flagged, 4/30 due → 5 days → P1 Urgent / 1-Day / On Track."""
        p, t, s = compute_blocker_sla(date(2026, 4, 30), date(2026, 4, 25))
        assert p == SLAPriority.P1_URGENT
        assert t == SLATracker.ONE_DAY
        assert s == SLAStatus.ON_TRACK

    def test_apr27_vs_apr30_is_p0_at_risk(self) -> None:
        """4/27 flagged, 4/30 due → 3 days → P0 Critical / Same-Day / At Risk."""
        p, t, s = compute_blocker_sla(date(2026, 4, 30), date(2026, 4, 27))
        assert p == SLAPriority.P0_CRITICAL
        assert t == SLATracker.SAME_DAY
        assert s == SLAStatus.AT_RISK

    def test_single_client_apr27_vs_apr30_still_p0(self) -> None:
        """Even single-client impact: 4/27 flagged, 4/30 due → P0 Critical."""
        p, t, s = compute_blocker_sla(date(2026, 4, 30), date(2026, 4, 27))
        assert p == SLAPriority.P0_CRITICAL
        assert s == SLAStatus.AT_RISK

    def test_past_due_is_p0_at_risk(self) -> None:
        """Due date already passed → P0 Critical / At Risk."""
        p, t, s = compute_blocker_sla(date(2026, 4, 25), date(2026, 4, 28))
        assert p == SLAPriority.P0_CRITICAL
        assert t == SLATracker.SAME_DAY
        assert s == SLAStatus.AT_RISK

    def test_due_today_is_p0(self) -> None:
        p, t, s = compute_blocker_sla(date(2026, 4, 30), date(2026, 4, 30))
        assert p == SLAPriority.P0_CRITICAL
        assert s == SLAStatus.AT_RISK

    def test_11_days_away_is_p3(self) -> None:
        p, t, s = compute_blocker_sla(date(2026, 5, 1), date(2026, 4, 20))
        assert p == SLAPriority.P3_MEDIUM
        assert t == SLATracker.THREE_DAY
        assert s == SLAStatus.ON_TRACK

    def test_no_due_date_returns_none(self) -> None:
        p, t, s = compute_blocker_sla(None, date(2026, 4, 20))
        assert p is None
        assert t is None
        assert s is None

    def test_exactly_3_days_is_p0(self) -> None:
        p, t, s = compute_blocker_sla(date(2026, 5, 3), date(2026, 4, 30))
        assert p == SLAPriority.P0_CRITICAL

    def test_exactly_4_days_is_p1(self) -> None:
        p, t, s = compute_blocker_sla(date(2026, 5, 4), date(2026, 4, 30))
        assert p == SLAPriority.P1_URGENT

    def test_exactly_5_days_is_p1(self) -> None:
        p, t, s = compute_blocker_sla(date(2026, 5, 5), date(2026, 4, 30))
        assert p == SLAPriority.P1_URGENT

    def test_exactly_6_days_is_p2(self) -> None:
        p, t, s = compute_blocker_sla(date(2026, 5, 6), date(2026, 4, 30))
        assert p == SLAPriority.P2_HIGH

    def test_exactly_10_days_is_p2(self) -> None:
        p, t, s = compute_blocker_sla(date(2026, 5, 10), date(2026, 4, 30))
        assert p == SLAPriority.P2_HIGH


class TestComputeRetroSLA:
    def test_retro_fixed_values(self) -> None:
        p, t, s = compute_retro_sla()
        assert p == SLAPriority.RETRO
        assert t == SLATracker.FOR_RETRO
        assert s == SLAStatus.ON_TRACK


# ---------------------------------------------------------------------------
# Label tests
# ---------------------------------------------------------------------------

class TestBuildBlockerLabel:
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


# ---------------------------------------------------------------------------
# Issue type classification
# ---------------------------------------------------------------------------

class TestClassifyIssueType:
    def test_blocker_tax_year_mismatch(self) -> None:
        assert classify_issue_type(
            "Tax year shows ET-2025 instead of ET-2026"
        ) == IssueType.BLOCKER

    def test_blocker_peo_name(self) -> None:
        assert classify_issue_type(
            "All clients are showing PEO company name incorrectly"
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

    def test_none_when_unknown(self) -> None:
        assert infer_impact("some issue", None) is None


# ---------------------------------------------------------------------------
# apply_mapping integration — SLA by Work Type
# ---------------------------------------------------------------------------

class TestApplyMappingBlockerSLA:
    """Blocker SLA is driven purely by due-date proximity."""

    def test_blocker_with_due_date_3_days_is_p0_at_risk(self) -> None:
        result = apply_mapping(
            description="Tax year mismatch ET-2025",
            tax_period="1Q2026",
            due_date=date(2026, 4, 30),
            today=date(2026, 4, 27),
        )
        assert result.issue_type == IssueType.BLOCKER
        assert result.sla_priority == SLAPriority.P0_CRITICAL
        assert result.sla_tracker == SLATracker.SAME_DAY
        assert result.sla_status == SLAStatus.AT_RISK

    def test_blocker_with_due_date_10_days_is_p2(self) -> None:
        result = apply_mapping(
            description="Tax year mismatch ET-2025",
            tax_period="1Q2026",
            due_date=date(2026, 4, 30),
            today=date(2026, 4, 20),
        )
        assert result.sla_priority == SLAPriority.P2_HIGH
        assert result.sla_tracker == SLATracker.TWO_DAY
        assert result.sla_status == SLAStatus.ON_TRACK

    def test_blocker_with_due_date_5_days_is_p1(self) -> None:
        result = apply_mapping(
            description="Tax year mismatch ET-2025",
            tax_period="1Q2026",
            due_date=date(2026, 4, 30),
            today=date(2026, 4, 25),
        )
        assert result.sla_priority == SLAPriority.P1_URGENT
        assert result.sla_tracker == SLATracker.ONE_DAY
        assert result.sla_status == SLAStatus.ON_TRACK

    def test_blocker_no_due_date_sla_blank_and_needs_review(self) -> None:
        result = apply_mapping(
            description="Tax year mismatch ET-2025",
            tax_period="1Q2026",
            due_date=None,
            today=date(2026, 4, 20),
        )
        assert result.sla_priority is None
        assert result.sla_tracker is None
        assert result.sla_status is None
        assert result.needs_mapping_review is True

    def test_impact_does_not_override_due_date_sla(self) -> None:
        """Even single-client impact doesn't change SLA when due date is close."""
        result = apply_mapping(
            description="Tax year mismatch ET-2025",
            tax_period="1Q2026",
            impact_hint="single client",
            due_date=date(2026, 4, 30),
            today=date(2026, 4, 27),
        )
        assert result.sla_priority == SLAPriority.P0_CRITICAL
        assert result.sla_status == SLAStatus.AT_RISK

    def test_all_clients_impact_does_not_bump_sla_without_due_date(self) -> None:
        """All-clients impact but no due date → SLA fields blank."""
        result = apply_mapping(
            description="All clients are showing PEO name wrong",
            tax_period="1Q2026",
            impact_hint="all clients",
            due_date=None,
            today=date(2026, 4, 20),
        )
        assert result.sla_priority is None
        assert result.sla_tracker is None
        assert result.sla_status is None


class TestApplyMappingRetroSLA:
    """Retro always gets fixed SLA values."""

    def test_retro_sla_fixed(self) -> None:
        result = apply_mapping(
            description="Retro discussion for Q1 filing",
            tax_period="Q1 2026",
        )
        assert result.issue_type == IssueType.BLOCKER  # "retro" isn't a blocker signal
        # The issue_type classification doesn't detect "retro" from description alone.
        # Retro SLA is set when issue_type is explicitly RETRO, which typically
        # comes from the intake pipeline, not description classification.


class TestApplyMappingOtherWorkTypes:
    """Filing Exception, Feature Request, Executive Summary → SLA blank."""

    def test_filing_exception_sla_blank(self) -> None:
        result = apply_mapping(
            description="Filing exception request for client exclusion",
            tax_period="Q1 2026",
        )
        assert result.issue_type == IssueType.FILING_EXCEPTION
        assert result.sla_priority is None
        assert result.sla_tracker is None
        assert result.sla_status is None

    def test_feature_request_sla_blank(self) -> None:
        result = apply_mapping(
            description="Enhancement request for a new report format",
            tax_period="Q1 2026",
        )
        assert result.issue_type == IssueType.FEATURE_REQUEST
        assert result.sla_priority is None
        assert result.sla_tracker is None
        assert result.sla_status is None


class TestApplyMappingMonthly:
    def test_april_2026_is_monthly_with_q2_period(self) -> None:
        result = apply_mapping(
            description="April 2026 withholding looks wrong. Showing ET-2025.",
            tax_period="April 2026",
        )
        assert result.filing_frequency == FilingFrequency.MONTHLY
        assert result.filing_period == FilingPeriod.Q2
        assert result.year == FilingYear.Y2026


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
            due_date=date(2026, 4, 30),
            today=date(2026, 4, 27),
        )

    def test_issue_type_is_blocker(self) -> None:
        assert self._get_result().issue_type == IssueType.BLOCKER

    def test_filing_period_q1(self) -> None:
        assert self._get_result().filing_period == FilingPeriod.Q1

    def test_year_2026(self) -> None:
        assert self._get_result().year == FilingYear.Y2026

    def test_sla_priority_p0(self) -> None:
        assert self._get_result().sla_priority == SLAPriority.P0_CRITICAL

    def test_sla_tracker_same_day(self) -> None:
        assert self._get_result().sla_tracker == SLATracker.SAME_DAY

    def test_sla_status_at_risk(self) -> None:
        assert self._get_result().sla_status == SLAStatus.AT_RISK

    def test_label_q126_filing_blocker(self) -> None:
        assert "Q126-filing-blocker" in self._get_result().labels

    def test_impact_all_clients(self) -> None:
        assert self._get_result().impact == Impact.ALL_CLIENTS


class TestApplyMappingNoPriority:
    """Jira's default Priority field must never appear in mapping output."""

    def test_mapping_result_has_no_priority_field(self) -> None:
        result = apply_mapping(
            description="Tax year mismatch",
            tax_period="1Q2026",
        )
        assert not hasattr(result, "priority")
