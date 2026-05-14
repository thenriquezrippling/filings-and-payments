"""Tests for the Jira client (Phase 3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tax_ops_filing_bot.jira.client import (
    JiraClient,
    JiraClientError,
    JiraConfig,
    _priority_label_to_name,
    _text_to_adf,
)


@pytest.fixture
def config() -> JiraConfig:
    return JiraConfig(
        base_url="https://test.atlassian.net",
        email="bot@test.com",
        api_token="fake-token",
    )


@pytest.fixture
def mock_httpx() -> MagicMock:
    with patch("tax_ops_filing_bot.jira.client.httpx.Client") as mock_cls:
        yield mock_cls.return_value


class TestTextToAdf:
    def test_single_paragraph(self) -> None:
        adf = _text_to_adf("Hello world")
        assert adf["type"] == "doc"
        assert adf["version"] == 1
        assert len(adf["content"]) == 1
        assert adf["content"][0]["content"][0]["text"] == "Hello world"

    def test_multiple_paragraphs(self) -> None:
        adf = _text_to_adf("Para 1\n\nPara 2\n\nPara 3")
        assert len(adf["content"]) == 3


class TestPriorityMapping:
    def test_known_priorities(self) -> None:
        assert _priority_label_to_name("P0") == "Highest"
        assert _priority_label_to_name("P1") == "High"
        assert _priority_label_to_name("P2") == "Medium"
        assert _priority_label_to_name("P3") == "Low"
        assert _priority_label_to_name("P4") == "Lowest"

    def test_unknown_priority(self) -> None:
        assert _priority_label_to_name("P99") == "Medium"


class TestJiraClientCreateIssue:
    def test_create_basic_issue(self, config: JiraConfig, mock_httpx: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "key": "FILING-9999",
            "id": "10001",
            "self": "https://test.atlassian.net/rest/api/3/issue/10001",
        }
        mock_httpx.post.return_value = mock_resp

        client = JiraClient(config)
        issue = client.create_issue(
            summary="Test issue",
            description="Test description",
        )
        assert issue.key == "FILING-9999"
        assert issue.id == "10001"

        call_args = mock_httpx.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["fields"]["summary"] == "Test issue"
        assert payload["fields"]["project"]["key"] == "FILING"

    def test_create_with_labels_and_parent(self, config: JiraConfig, mock_httpx: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "key": "FILING-1000",
            "id": "10002",
            "self": "https://test.atlassian.net/rest/api/3/issue/10002",
        }
        mock_httpx.post.return_value = mock_resp

        client = JiraClient(config)
        issue = client.create_issue(
            summary="Test",
            description="Desc",
            labels=["q1-2026", "peo"],
            parent_key="FILING-100",
            priority="P0",
        )
        assert issue.key == "FILING-1000"

        call_args = mock_httpx.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["fields"]["labels"] == ["q1-2026", "peo"]
        assert payload["fields"]["parent"]["key"] == "FILING-100"
        assert payload["fields"]["priority"]["name"] == "Highest"

    def test_api_error_raises(self, config: JiraConfig, mock_httpx: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"errors": {"summary": "required"}}
        mock_httpx.post.return_value = mock_resp

        client = JiraClient(config)
        with pytest.raises(JiraClientError, match="400"):
            client.create_issue(summary="", description="")


class TestJiraClientAddComment:
    def test_add_comment(self, config: JiraConfig, mock_httpx: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "comment-1"}
        mock_httpx.post.return_value = mock_resp

        client = JiraClient(config)
        result = client.add_comment("FILING-5911", "synced content")
        assert result["id"] == "comment-1"


class TestJiraClientTransition:
    def test_transition_found(self, config: JiraConfig, mock_httpx: MagicMock) -> None:
        get_resp = MagicMock()
        get_resp.is_success = True
        get_resp.json.return_value = {
            "transitions": [
                {"id": "31", "name": "Resolved"},
                {"id": "41", "name": "Closed"},
            ]
        }
        post_resp = MagicMock()
        post_resp.is_success = True
        post_resp.status_code = 204
        post_resp.json.return_value = {}

        mock_httpx.get.return_value = get_resp
        mock_httpx.post.return_value = post_resp

        client = JiraClient(config)
        client.transition_issue("FILING-1", "Resolved")

    def test_transition_not_found(self, config: JiraConfig, mock_httpx: MagicMock) -> None:
        get_resp = MagicMock()
        get_resp.is_success = True
        get_resp.json.return_value = {
            "transitions": [{"id": "31", "name": "Resolved"}]
        }
        mock_httpx.get.return_value = get_resp

        client = JiraClient(config)
        with pytest.raises(JiraClientError, match="not found"):
            client.transition_issue("FILING-1", "NonExistent")


class TestJiraClientContextManager:
    def test_context_manager(self, config: JiraConfig, mock_httpx: MagicMock) -> None:
        with JiraClient(config) as _client:
            pass
        mock_httpx.close.assert_called_once()
