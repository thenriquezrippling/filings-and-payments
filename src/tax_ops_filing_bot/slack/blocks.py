"""Block Kit builders for filing issue confirmation and sync feedback."""

from __future__ import annotations

from typing import Any

from tax_ops_filing_bot.models.schemas import FilingIssueDraft


def draft_confirmation_blocks(
    draft: FilingIssueDraft,
    thread_ts: str,
) -> list[dict[str, Any]]:
    """Build Block Kit blocks for confirming a FilingIssueDraft before Jira creation."""
    agency_display = draft.agency.value if draft.agency else "N/A"
    labels_display = ", ".join(draft.labels) if draft.labels else "none"
    entities_display = ", ".join(draft.affected_entity_ids) if draft.affected_entity_ids else "none"
    dri_display = draft.suggested_dri or "unassigned"

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "New FILING Ticket Draft", "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{draft.summary}*",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Category:* {draft.category.value}"},
                {"type": "mrkdwn", "text": f"*Agency:* {agency_display}"},
                {"type": "mrkdwn", "text": f"*Priority:* {draft.priority}"},
                {"type": "mrkdwn", "text": f"*DRI:* {dri_display}"},
                {"type": "mrkdwn", "text": f"*Labels:* {labels_display}"},
                {"type": "mrkdwn", "text": f"*Entities:* {entities_display}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Description:*\n{_truncate(draft.description, 2800)}",
            },
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Confidence: {draft.confidence:.0%} · thread_ts: {thread_ts}",
                },
            ],
        },
        {
            "type": "actions",
            "block_id": "filing_confirm_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Create Ticket"},
                    "style": "primary",
                    "action_id": "filing_create_confirm",
                    "value": thread_ts,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "style": "danger",
                    "action_id": "filing_create_cancel",
                    "value": thread_ts,
                },
            ],
        },
    ]
    return blocks


def issue_created_blocks(issue_key: str, summary: str) -> list[dict[str, Any]]:
    """Blocks posted after successful Jira issue creation."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Created *<{{jira_url}}/browse/{issue_key}|{issue_key}>*: {summary}",
            },
        },
    ]


def sync_success_blocks(issue_key: str, message_count: int) -> list[dict[str, Any]]:
    """Blocks posted after syncing a thread to an existing issue."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Synced {message_count} message(s) to "
                    f"*<{{jira_url}}/browse/{issue_key}|{issue_key}>*"
                ),
            },
        },
    ]


def error_blocks(error_message: str) -> list[dict[str, Any]]:
    """Blocks posted when an operation fails."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Something went wrong:\n```{_truncate(error_message, 2500)}```",
            },
        },
    ]


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
