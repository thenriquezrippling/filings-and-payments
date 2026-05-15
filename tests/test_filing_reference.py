"""Tests for epic child filing ticket matching and Jira link payloads."""

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
    enrich_draft_with_epic_children,
    jira_issue_link_payload,
    pick_related_filing_keys,
)


def _base_draft() -> FilingIssueDraft:
    return FilingIssueDraft(
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


class TestPickRelatedFilingKeys:
    def test_matches_quarterly_child(self) -> None:
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
        keys = pick_related_filing_keys(draft, children)
        assert keys == ["FILING-5001"]

    def test_ignores_non_filing_child_types(self) -> None:
        draft = _base_draft()
        children = [
            EpicChildIssue(
                key="FILING-6000",
                summary="Pennsylvania Q1 2026 Quarterly Local",
                issue_type_name="Blocker",
                duedate=None,
            ),
        ]
        assert pick_related_filing_keys(draft, children) == []


class TestEnrichDraftWithEpicChildren:
    def test_inherits_duedate_when_single_match(self) -> None:
        draft = _base_draft()
        children = [
            EpicChildIssue(
                key="FILING-5001",
                summary="Pennsylvania Q1 2026 Quarterly Local",
                issue_type_name="Quarterly",
                duedate="2026-04-30",
            ),
        ]
        enriched = enrich_draft_with_epic_children(draft, children)
        assert enriched.related_filing_issue_keys == ["FILING-5001"]
        assert enriched.due_date == "2026-04-30"

    def test_keeps_extracted_due_date_over_child(self) -> None:
        draft = _base_draft().model_copy(update={"due_date": "2026-05-01"})
        children = [
            EpicChildIssue(
                key="FILING-5001",
                summary="Pennsylvania Q1 2026 Quarterly Local",
                issue_type_name="Quarterly",
                duedate="2026-04-30",
            ),
        ]
        enriched = enrich_draft_with_epic_children(draft, children)
        assert enriched.due_date == "2026-05-01"


class TestJiraIssueLinkPayload:
    def test_relates_shape(self) -> None:
        body = jira_issue_link_payload("FILING-7000", "FILING-5001")
        assert body["type"]["name"] == "Relates"
        assert body["inwardIssue"]["key"] == "FILING-7000"
        assert body["outwardIssue"]["key"] == "FILING-5001"
