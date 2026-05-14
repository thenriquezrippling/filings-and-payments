"""Tests for the deterministic mapping layer (requirements F.2-F.5)."""

from __future__ import annotations

from tax_ops_filing_bot.models.filing import IssuePriority, IssueType
from tax_ops_filing_bot.services.mapping import (
    MappingResult,
    apply_mapping,
    resolve_filing_code,
)


class TestResoveFilingCode:
    def test_pittsburgh_payexp(self) -> None:
        result = resolve_filing_code("PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE")
        assert result is not None
        assert result["jurisdiction"] == "City of Pittsburgh"
        assert result["tax_type"] == "EIT"

    def test_unknown_code(self) -> None:
        result = resolve_filing_code("UNKNOWNAGENCYFILE")
        assert result is None


class TestApplyMappingPittsburghEIT:
    """Pittsburgh EIT must be classified as Blocker with correct epic and labels (F.2-F.4)."""

    def _get_pittsburgh_eit_result(self) -> MappingResult:
        return apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period="1Q2026",
            agency="PA Local Treasurer - City of Pittsburgh",
            filing_code="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE",
            description=(
                "Tax year at top of return displays ET-2025 but should read "
                "ET-2026. All clients are showing Rippling PEO 1, Inc. as "
                "Company Name of Professional Employer Organization."
            ),
        )

    def test_issue_type_is_blocker(self) -> None:
        """F.2: Pittsburgh EIT is classified as Blocker."""
        result = self._get_pittsburgh_eit_result()
        assert result.issue_type == IssueType.BLOCKER

    def test_priority_is_highest(self) -> None:
        result = self._get_pittsburgh_eit_result()
        assert result.priority == IssuePriority.HIGHEST

    def test_parent_epic_from_mapping(self) -> None:
        """F.3: Parent epic is selected from the mapping layer."""
        result = self._get_pittsburgh_eit_result()
        assert result.parent_epic_key == "FILING-101"

    def test_labels_include_jurisdiction(self) -> None:
        """F.4: Labels include jurisdiction."""
        result = self._get_pittsburgh_eit_result()
        assert "pittsburgh" in result.labels

    def test_labels_include_state_label(self) -> None:
        """F.4: Labels include state/local designation."""
        result = self._get_pittsburgh_eit_result()
        assert "pa-local" in result.labels

    def test_labels_include_tax_type(self) -> None:
        """F.4: Labels include tax type."""
        result = self._get_pittsburgh_eit_result()
        assert "eit" in result.labels

    def test_labels_include_period(self) -> None:
        """F.4: Labels include filing period."""
        result = self._get_pittsburgh_eit_result()
        assert "q1-2026" in result.labels

    def test_labels_include_blocker_designation(self) -> None:
        """F.4: Labels include blocker designation."""
        result = self._get_pittsburgh_eit_result()
        assert "filing-blocker" in result.labels

    def test_labels_include_form_output(self) -> None:
        """F.4: Labels include form-output for PEO / form display issues."""
        result = self._get_pittsburgh_eit_result()
        assert "form-output" in result.labels

    def test_labels_include_payroll_expense_tax(self) -> None:
        """F.4: Labels include issue category from mapping."""
        result = self._get_pittsburgh_eit_result()
        assert "payroll-expense-tax" in result.labels

    def test_needs_mapping_review_false(self) -> None:
        result = self._get_pittsburgh_eit_result()
        assert result.needs_mapping_review is False


class TestApplyMappingFromFilingCode:
    """Filing code should be resolved to populate missing metadata."""

    def test_filing_code_resolves_jurisdiction(self) -> None:
        result = apply_mapping(
            jurisdiction=None,
            tax_type=None,
            tax_period="1Q2026",
            agency=None,
            filing_code="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE",
            description="Tax year showing ET-2025 instead of ET-2026",
        )
        assert result.parent_epic_key == "FILING-101"
        assert "pittsburgh" in result.labels
        assert result.needs_mapping_review is False


class TestApplyMappingUnmappedAgency:
    """F.5: Unmapped agencies set needs_mapping_review = true."""

    def test_unknown_jurisdiction(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Denver",
            tax_type="OPT",
            tax_period="2Q2026",
            agency="Denver Revenue",
            filing_code=None,
            description="Occupational privilege tax amount is incorrect.",
        )
        assert result.needs_mapping_review is True
        assert result.parent_epic_key is None

    def test_unknown_jurisdiction_still_classifies(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Denver",
            tax_type="OPT",
            tax_period="2Q2026",
            agency="Denver Revenue",
            filing_code=None,
            description="Tax amount is incorrect, showing wrong period.",
        )
        assert result.issue_type in list(IssueType)
        assert result.priority in list(IssuePriority)

    def test_unknown_jurisdiction_has_basic_labels(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Denver",
            tax_type="OPT",
            tax_period="2Q2026",
            agency="Denver Revenue",
            filing_code=None,
            description="Filing issue.",
        )
        assert "city-of-denver" in result.labels
        assert "opt" in result.labels
        assert "q2-2026" in result.labels

    def test_completely_unknown(self) -> None:
        result = apply_mapping(
            jurisdiction=None,
            tax_type=None,
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Something is wrong with a filing.",
        )
        assert result.needs_mapping_review is True
        assert result.parent_epic_key is None


class TestClassificationRules:
    """Test issue type classification from description signals."""

    def test_blocker_data_mismatch(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Data mismatch: account number is wrong.",
        )
        assert result.issue_type == IssueType.BLOCKER

    def test_blocker_wrong_year(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Form showing ET-2024 but should be ET-2025.",
        )
        assert result.issue_type == IssueType.BLOCKER

    def test_blocker_missing_account(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Missing account number on the filing.",
        )
        assert result.issue_type == IssueType.BLOCKER

    def test_incident_systemic_failure(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Systemic failure in the filing platform today.",
        )
        assert result.issue_type == IssueType.INCIDENT

    def test_incident_production_outage(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Production outage affecting filing submissions.",
        )
        assert result.issue_type == IssueType.INCIDENT

    def test_filing_exception_after_submission(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Issue found after submission, needs amendment.",
        )
        assert result.issue_type == IssueType.FILING_EXCEPTION

    def test_feature_request(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="Enhancement request for a new report format.",
        )
        assert result.issue_type == IssueType.FEATURE_REQUEST

    def test_process_improvement(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period=None,
            agency=None,
            filing_code=None,
            description="SOP update needed for the review workflow.",
        )
        assert result.issue_type == IssueType.PROCESS_IMPROVEMENT


class TestPeriodNormalization:
    def test_1q2026(self) -> None:
        result = apply_mapping(
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period="1Q2026",
            agency=None,
            filing_code=None,
            description="Tax year showing ET-2025 instead of 2026.",
        )
        assert "q1-2026" in result.labels

    def test_fiscal_year(self) -> None:
        result = apply_mapping(
            jurisdiction="Unknown Place",
            tax_type="ABC",
            tax_period="FY2025",
            agency=None,
            filing_code=None,
            description="Issue with filing.",
        )
        assert "fy-2025" in result.labels

    def test_plain_year(self) -> None:
        result = apply_mapping(
            jurisdiction="Unknown Place",
            tax_type="ABC",
            tax_period="2026",
            agency=None,
            filing_code=None,
            description="Issue with filing.",
        )
        assert "2026" in result.labels
