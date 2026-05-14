"""Jira Cloud REST API v3 client for the FILING project."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_V3 = "/rest/api/3"


@dataclass(frozen=True)
class JiraIssue:
    """Minimal representation of a created / fetched Jira issue."""

    key: str
    id: str
    self_url: str


@dataclass
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    project_key: str = "FILING"
    timeout: float = 30.0


class JiraClientError(Exception):
    """Raised on non-recoverable Jira API errors."""


class JiraClient:
    """Async-capable Jira Cloud REST client using httpx."""

    def __init__(self, config: JiraConfig) -> None:
        self._config = config
        self._http = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            auth=(config.email, config.api_token),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=config.timeout,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> JiraClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def create_issue(
        self,
        summary: str,
        description: str,
        *,
        issue_type: str = "Bug",
        priority: str | None = None,
        labels: list[str] | None = None,
        parent_key: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> JiraIssue:
        """Create a new issue in the configured FILING project.

        ``description`` is sent as Atlassian Document Format (ADF) with a
        single paragraph node. For richer formatting the caller can pass a
        pre-built ADF tree via ``extra_fields``.
        """
        fields: dict[str, Any] = {
            "project": {"key": self._config.project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "description": _text_to_adf(description),
        }
        if priority:
            fields["priority"] = {"name": _priority_label_to_name(priority)}
        if labels:
            fields["labels"] = labels
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if extra_fields:
            fields.update(extra_fields)

        resp = self._post(f"{_API_V3}/issue", {"fields": fields})
        return JiraIssue(
            key=resp["key"],
            id=resp["id"],
            self_url=resp["self"],
        )

    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """Append a comment (ADF paragraph) to an existing issue."""
        payload = {"body": _text_to_adf(body)}
        return self._post(f"{_API_V3}/issue/{issue_key}/comment", payload)

    def get_issue(self, issue_key: str, *, fields: str = "summary,status,assignee") -> dict[str, Any]:
        """Fetch an issue by key with selected fields."""
        resp = self._http.get(
            f"{_API_V3}/issue/{issue_key}",
            params={"fields": fields},
        )
        self._raise_for_status(resp)
        return resp.json()

    def transition_issue(self, issue_key: str, transition_name: str) -> None:
        """Transition an issue by human-readable transition name."""
        transitions = self._get_transitions(issue_key)
        match = next(
            (t for t in transitions if t["name"].lower() == transition_name.lower()),
            None,
        )
        if match is None:
            available = [t["name"] for t in transitions]
            raise JiraClientError(
                f"Transition '{transition_name}' not found for {issue_key}. "
                f"Available: {available}"
            )
        self._post(
            f"{_API_V3}/issue/{issue_key}/transitions",
            {"transition": {"id": match["id"]}},
        )

    def add_labels(self, issue_key: str, labels: list[str]) -> None:
        """Add labels to an issue without removing existing ones."""
        update_payload = {
            "update": {
                "labels": [{"add": label} for label in labels],
            }
        }
        resp = self._http.put(
            f"{_API_V3}/issue/{issue_key}",
            json=update_payload,
        )
        self._raise_for_status(resp)

    def _get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        resp = self._http.get(f"{_API_V3}/issue/{issue_key}/transitions")
        self._raise_for_status(resp)
        return resp.json()["transitions"]

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.post(path, json=payload)
        self._raise_for_status(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise JiraClientError(
            f"Jira API error {resp.status_code}: {detail}"
        )


def _text_to_adf(text: str) -> dict[str, Any]:
    """Convert plain text to a minimal ADF document."""
    paragraphs = text.split("\n\n") if "\n\n" in text else [text]
    content_nodes = []
    for para in paragraphs:
        content_nodes.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": para}],
        })
    return {
        "type": "doc",
        "version": 1,
        "content": content_nodes,
    }


_PRIORITY_MAP: dict[str, str] = {
    "P0": "Highest",
    "P1": "High",
    "P2": "Medium",
    "P3": "Low",
    "P4": "Lowest",
}


def _priority_label_to_name(label: str) -> str:
    return _PRIORITY_MAP.get(label, "Medium")
