"""Block Kit payloads for the filing confirmation UI."""

from __future__ import annotations

from typing import Any

from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft


def build_confirmation_blocks(
    draft: FilingIssueDraft,
    *,
    thread_ts: str,
    channel_id: str,
) -> list[dict[str, Any]]:
    """Return Slack Block Kit blocks for a filing confirmation message.

    The user sees a summary of the inferred Jira fields and can approve or
    reject the ticket creation via action buttons.  The ``action_id`` values
    (``filing_approve`` / ``filing_reject``) encode the thread context so the
    action handler can correlate the response.
    """
    label_str = ", ".join(draft.labels) if draft.labels else "_none_"
    parent_str = draft.parent_key or "_none_"
    assignee_str = draft.assignee_hint or "_unassigned_"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 New FILING ticket draft"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Summary:*\n{draft.summary}"},
                {"type": "mrkdwn", "text": f"*Type:* {draft.issue_type.value}"},
                {"type": "mrkdwn", "text": f"*Priority:* {draft.priority.value}"},
                {"type": "mrkdwn", "text": f"*Labels:* {label_str}"},
                {"type": "mrkdwn", "text": f"*Epic:* {parent_str}"},
                {"type": "mrkdwn", "text": f"*Assignee hint:* {assignee_str}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Description:*\n{_truncate(draft.description, 2000)}",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Create ticket"},
                    "style": "primary",
                    "action_id": "filing_approve",
                    "value": f"{channel_id}|{thread_ts}",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Cancel"},
                    "style": "danger",
                    "action_id": "filing_reject",
                    "value": f"{channel_id}|{thread_ts}",
                },
            ],
        },
    ]


def build_created_message(issue_key: str, base_url: str = "") -> list[dict[str, Any]]:
    """Blocks posted after successful ticket creation."""
    link = f"{base_url}/browse/{issue_key}" if base_url else issue_key
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"✅ Created *<{link}|{issue_key}>*" if base_url else f"✅ Created *{issue_key}*",
            },
        },
    ]


def build_sync_message(issue_key: str) -> list[dict[str, Any]]:
    """Blocks posted after syncing a thread to an existing issue."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔄 Synced thread to *{issue_key}*",
            },
        },
    ]


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
