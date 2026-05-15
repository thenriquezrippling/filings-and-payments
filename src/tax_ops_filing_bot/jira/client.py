"""Jira Cloud REST API client with mock mode for local development."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from tax_ops_filing_bot.jira.payload import build_comment_payload, build_create_payload
from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft

logger = logging.getLogger(__name__)


@dataclass
class CreatedIssue:
    key: str
    issue_id: str
    self_url: str


@dataclass
class JiraClient:
    """Jira Cloud REST v3 client.

    When ``base_url`` is the sentinel ``"mock"`` the client skips HTTP and
    returns deterministic fake responses so the full workflow is testable
    without credentials.
    """

    base_url: str
    email: str = ""
    api_token: str = ""
    project_key: str = "FILING"

    _mock_counter: int = field(default=0, init=False, repr=False)

    MOCK_SENTINEL = "mock"

    @property
    def is_mock(self) -> bool:
        return self.base_url == self.MOCK_SENTINEL

    def create_issue(self, draft: FilingIssueDraft) -> CreatedIssue:
        payload = build_create_payload(draft, project_key=self.project_key)

        if self.is_mock:
            self._mock_counter += 1
            key = f"{self.project_key}-{self._mock_counter}"
            logger.info("Mock Jira: created %s", key)
            return CreatedIssue(
                key=key,
                issue_id=str(10000 + self._mock_counter),
                self_url=f"https://mock.atlassian.net/rest/api/3/issue/{10000 + self._mock_counter}",
            )

        return self._post_issue(payload)

    def add_comment(self, issue_key: str, text: str) -> dict[str, Any]:
        payload = build_comment_payload(text)

        if self.is_mock:
            logger.info("Mock Jira: added comment to %s", issue_key)
            return {"id": "90001", "self": f"https://mock.atlassian.net/rest/api/3/issue/{issue_key}/comment/90001"}

        return self._post_comment(issue_key, payload)

    def get_issue(self, issue_key: str) -> Optional[dict[str, Any]]:
        if self.is_mock:
            return {
                "key": issue_key,
                "fields": {"summary": f"Mock issue {issue_key}", "status": {"name": "To Do"}},
            }

        return self._get(f"/rest/api/3/issue/{issue_key}")

    def _auth(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(username=self.email, password=self.api_token)

    def _post_issue(self, payload: dict[str, Any]) -> CreatedIssue:
        url = f"{self.base_url}/rest/api/3/issue"
        with httpx.Client() as client:
            resp = client.post(url, json=payload, auth=self._auth(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return CreatedIssue(key=data["key"], issue_id=data["id"], self_url=data["self"])

    def _post_comment(self, issue_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        with httpx.Client() as client:
            resp = client.post(url, json=payload, auth=self._auth(), timeout=30)
            resp.raise_for_status()
            return resp.json()

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client() as client:
            resp = client.get(url, auth=self._auth(), timeout=30)
            resp.raise_for_status()
            return resp.json()
