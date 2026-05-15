"""Tests for epic child filing ticket matching and Jira link payloads.

Matching rules:
  - Filing unit mismatch → skip candidate
  - Multiple tied candidates → needs_mapping_review=True, no auto-link
  - PA matches Pennsylvania but NOT payroll (word-boundary matching)
  - Year matching contributes score only once (no double-counting)
"""

from __future__ import annotations

from tax_ops_filing_bot.models.filing import (
    FilingFrequency,
    FilingIssueDraft,
    FilingPeriod,
    FilingYear,
    IssueType,
)
from tax_ops_filing_bot.services.filing_reference import (
    EpicChildIssue,
    _score_child,
    _state_matches,
    enrich_draft_with_epic_children,
    jira_issue_link_payload,
    pick_related_filing_keys,
)


def _base_draft(**overrides) -> FilingIssueDraft:
    defaults = dict(
        summary="Pittsburgh EIT display issue",
        description="Tax year shows ET-2025 instead of ET-2026.",
        issue_type=IssueType.BLOCKER,
        labels=["Q126-filing-blocker"],
        state="PA",
        filing_period=FilingPeriod.Q1,
        year=FilingYear.Y2026,
        filing_frequency=FilingFrequency.QUARTERLY,
        filing_unit_code="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE",
    )
    defaults.update(overrides)
    return FilingIssueDraft(**defaults)


class TestStateMatching:
    """PA must match Pennsylvania but NOT payroll."""

    def test_pa_matches_pennsylvania(self) -> None:
        assert _state_matches("PA", "pennsylvania q1 2026 quarterly local") is True

    def test_pa_matches_pa_word(self) -> None:
        assert _state_matches("PA", "pa q1 2026 quarterly") is True

    def test_pa_does_not_match_payroll(self) -> None:
        assert _state_matches("PA", "semi-monthly payroll tax schedule") is False

    def test_pa_does_not_match_separate(self) -> None:
        assert _state_matches("PA", "comparable data analysis") is False

    def test_pa_does_not_match_payment(self) -> None:
        assert _state_matches("PA", "quarterly payment processing") is False

    def test_full_name_matches(self) -> None:
        assert _state_matches("pennsylvania", "pennsylvania q1 2026") is True

    def test_ny_matches_new_york(self) -> None:
        assert _state_matches("NY", "new york quarterly filing") is True

    def test_none_state(self) -> None:
        assert _state_matches(None, "anything") is False


class TestYearMatchingNoDoubleCount:
    """Year contributes to score only once, even when both '2026' and '26' match."""

    def test_year_scores_once(self) -> None:
        draft = _base_draft()
        child = EpicChildIssue(
            key="FILING-5001",
            summary=(
                "Pennsylvania Q1 2026 Quarterly Local — "
                "PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE"
            ),
            issue_type_name="Quarterly",
        )
        score = _score_child(draft, child)

        draft_no_year = _base_draft(year=None)
        score_no_year = _score_child(draft_no_year, child)

        assert score - score_no_year == 1


class TestFilingUnitRequired:
    """Filing unit mismatch must skip the candidate entirely."""

    def test_filing_unit_mismatch_scores_zero(self) -> None:
        draft = _base_draft()
        child = EpicChildIssue(
            key="FILING-6000",
            summary="Pennsylvania Q1 2026 Quarterly Local — PADEPTOFREVENUEFILE",
            issue_type_name="Quarterly",
        )
        assert _score_child(draft, child) == 0

    def test_no_filing_unit_on_draft_still_scores(self) -> None:
        draft = _base_draft(filing_unit_code=None)
        child = EpicChildIssue(
            key="FILING-5001",
            summary="Pennsylvania Q1 2026 Quarterly Local",
            issue_type_name="Quarterly",
        )
        assert _score_child(draft, child) > 0


class TestPickRelatedFilingKeys:
    def test_single_strong_match(self) -> None:
        draft = _base_draft()
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
            EpicChildIssue(
                key="FILING-9999",
                summary="Unrelated W-2 batch",
                issue_type_name="W-2",
                duedate=None,
            ),
        ]
        keys, needs_review = pick_related_filing_keys(draft, children)
        assert keys == ["FILING-5001"]
        assert needs_review is False

    def test_ignores_non_filing_child_types(self) -> None:
        draft = _base_draft()
        children = [
            EpicChildIssue(
                key="FILING-6000",
                summary="Pennsylvania Q1 2026 Quarterly Local",
                issue_type_name="Blocker",
            ),
        ]
        keys, needs_review = pick_related_filing_keys(draft, children)
        assert keys == []
        assert needs_review is True

    def test_multiple_tied_candidates_sets_needs_review(self) -> None:
        """Two children with identical scores → no auto-link, needs review."""
        draft = _base_draft(filing_unit_code=None)
        children = [
            EpicChildIssue(
                key="FILING-5001",
                summary="Pennsylvania Q1 2026 Quarterly Local — EIT",
                issue_type_name="Quarterly",
            ),
            EpicChildIssue(
                key="FILING-5002",
                summary="Pennsylvania Q1 2026 Quarterly Local — LST",
                issue_type_name="Quarterly",
            ),
        ]
        keys, needs_review = pick_related_filing_keys(draft, children)
        assert keys == []
        assert needs_review is True

    def test_no_match_above_threshold_sets_needs_review(self) -> None:
        draft = _base_draft()
        children = [
            EpicChildIssue(
                key="FILING-9999",
                summary="Unrelated stuff",
                issue_type_name="Quarterly",
            ),
        ]
        keys, needs_review = pick_related_filing_keys(draft, children)
        assert keys == []
        assert needs_review is True


class TestEnrichDraftWithEpicChildren:
    def test_inherits_duedate_from_single_match(self) -> None:
        draft = _base_draft()
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
        enriched = enrich_draft_with_epic_children(draft, children)
        assert enriched.related_filing_issue_keys == ["FILING-5001"]
        assert enriched.due_date == "2026-04-30"

    def test_does_not_inherit_duedate_on_tie(self) -> None:
        draft = _base_draft(filing_unit_code=None)
        children = [
            EpicChildIssue(
                key="FILING-5001",
                summary="Pennsylvania Q1 2026 Quarterly Local — EIT",
                issue_type_name="Quarterly",
                duedate="2026-04-30",
            ),
            EpicChildIssue(
                key="FILING-5002",
                summary="Pennsylvania Q1 2026 Quarterly Local — LST",
                issue_type_name="Quarterly",
                duedate="2026-05-15",
            ),
        ]
        enriched = enrich_draft_with_epic_children(draft, children)
        assert enriched.related_filing_issue_keys == []
        assert enriched.due_date is None
        assert enriched.needs_mapping_review is True


class TestJiraIssueLinkPayload:
    def test_relates_shape(self) -> None:
        body = jira_issue_link_payload("FILING-7000", "FILING-5001")
        assert body["type"]["name"] == "Relates"
        assert body["inwardIssue"]["key"] == "FILING-7000"
        assert body["outwardIssue"]["key"] == "FILING-5001"

    def test_custom_link_type(self) -> None:
        body = jira_issue_link_payload("A-1", "B-2", link_type_name="Blocks")
        assert body["type"]["name"] == "Blocks"
