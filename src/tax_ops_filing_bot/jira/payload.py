"""Build Jira REST API v3 payloads from a FilingIssueDraft."""

from __future__ import annotations

from typing import Any

from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft


def build_create_payload(
    draft: FilingIssueDraft,
    project_key: str = "FILING",
) -> dict[str, Any]:
    """Return a dict suitable for ``POST /rest/api/3/issue``."""
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": draft.summary,
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": draft.description}],
                }
            ],
        },
        "issuetype": {"name": draft.issue_type.value},
        "priority": {"name": draft.priority.value},
    }

    if draft.labels:
        fields["labels"] = draft.labels

    if draft.parent_key:
        fields["parent"] = {"key": draft.parent_key}

    return {"fields": fields}


def build_comment_payload(text: str) -> dict[str, Any]:
    """Return an ADF comment body for ``POST /rest/api/3/issue/{key}/comment``."""
    return {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }
    }
