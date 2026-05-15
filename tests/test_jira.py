"""Tests for Jira payload builder and mock client (Phase 3)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.jira.client import JiraClient, CreatedIssue
from tax_ops_filing_bot.jira.payload import build_create_payload, build_comment_payload
from tax_ops_filing_bot.models.issue_draft import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
)


def _sample_draft(**overrides) -> FilingIssueDraft:
    defaults = dict(
        summary="Pittsburgh EIT filing blocked",
        description="Cannot complete EIT filing for Pittsburgh municipality.",
        issue_type=IssueType.BLOCKER,
        priority=IssuePriority.HIGH,
        labels=["local-tax", "pittsburgh"],
        parent_key="FILING-101",
    )
    defaults.update(overrides)
    return FilingIssueDraft(**defaults)


class TestBuildCreatePayload:
    def test_basic_payload_structure(self) -> None:
        draft = _sample_draft()
        payload = build_create_payload(draft)
        fields = payload["fields"]
        assert fields["project"]["key"] == "FILING"
        assert fields["summary"] == "Pittsburgh EIT filing blocked"
        assert fields["issuetype"]["name"] == "Blocker"
        assert fields["priority"]["name"] == "High"

    def test_labels(self) -> None:
        draft = _sample_draft()
        payload = build_create_payload(draft)
        assert payload["fields"]["labels"] == ["local-tax", "pittsburgh"]

    def test_no_labels(self) -> None:
        draft = _sample_draft(labels=[])
        payload = build_create_payload(draft)
        assert "labels" not in payload["fields"]

    def test_parent_key(self) -> None:
        draft = _sample_draft(parent_key="FILING-101")
        payload = build_create_payload(draft)
        assert payload["fields"]["parent"]["key"] == "FILING-101"

    def test_no_parent_key(self) -> None:
        draft = _sample_draft(parent_key=None)
        payload = build_create_payload(draft)
        assert "parent" not in payload["fields"]

    def test_custom_project_key(self) -> None:
        draft = _sample_draft()
        payload = build_create_payload(draft, project_key="TAX")
        assert payload["fields"]["project"]["key"] == "TAX"

    def test_description_adf_format(self) -> None:
        draft = _sample_draft()
        payload = build_create_payload(draft)
        desc = payload["fields"]["description"]
        assert desc["type"] == "doc"
        assert desc["version"] == 1
        assert desc["content"][0]["type"] == "paragraph"
        assert desc["content"][0]["content"][0]["text"] == draft.description

    def test_all_work_types(self) -> None:
        for wt in IssueType:
            draft = _sample_draft(issue_type=wt)
            payload = build_create_payload(draft)
            assert payload["fields"]["issuetype"]["name"] == wt.value

    def test_filing_exception_type(self) -> None:
        draft = _sample_draft(issue_type=IssueType.FILING_EXCEPTION)
        payload = build_create_payload(draft)
        assert payload["fields"]["issuetype"]["name"] == "Filing Exception"

    def test_feature_request_type(self) -> None:
        draft = _sample_draft(issue_type=IssueType.FEATURE_REQUEST)
        payload = build_create_payload(draft)
        assert payload["fields"]["issuetype"]["name"] == "Feature Request"


class TestBuildCommentPayload:
    def test_comment_structure(self) -> None:
        payload = build_comment_payload("Thread synced from Slack")
        body = payload["body"]
        assert body["type"] == "doc"
        assert body["content"][0]["content"][0]["text"] == "Thread synced from Slack"


class TestJiraClientMock:
    def test_is_mock(self) -> None:
        client = JiraClient(base_url="mock")
        assert client.is_mock

    def test_not_mock(self) -> None:
        client = JiraClient(base_url="https://example.atlassian.net")
        assert not client.is_mock

    def test_create_issue(self) -> None:
        client = JiraClient(base_url="mock", project_key="FILING")
        draft = _sample_draft()
        result = client.create_issue(draft)
        assert isinstance(result, CreatedIssue)
        assert result.key == "FILING-1"
        assert result.issue_id == "10001"

    def test_create_issue_increments(self) -> None:
        client = JiraClient(base_url="mock", project_key="FILING")
        draft = _sample_draft()
        r1 = client.create_issue(draft)
        r2 = client.create_issue(draft)
        assert r1.key == "FILING-1"
        assert r2.key == "FILING-2"

    def test_add_comment(self) -> None:
        client = JiraClient(base_url="mock")
        result = client.add_comment("FILING-1", "Thread content here")
        assert "id" in result
        assert "self" in result

    def test_get_issue(self) -> None:
        client = JiraClient(base_url="mock")
        result = client.get_issue("FILING-42")
        assert result is not None
        assert result["key"] == "FILING-42"
        assert "summary" in result["fields"]
