"""Jira <-> Slack thread synchronization.

After ticket creation:
  1. Post ``Sync [FILING-KEY]`` into the Slack thread
  2. Add a Jira comment with Slack channel, thread_ts, permalink, and transcript

For sync-only (``sync this thread to FILING-1234``):
  1. Add Slack context as Jira comment
  2. Post ``Sync [FILING-1234]`` into the Slack thread
  3. Do NOT create a new Jira issue

Deduplication:
  - If the thread already contains ``Sync [FILING-KEY]``, do not post again.
  - If the Jira issue already has a comment referencing the same thread_ts,
    do not add another comment.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_SYNC_MARKER_RE = re.compile(r"Sync\s+\[([A-Z]+-\d+)\]")
_SYNC_COMMAND_RE = re.compile(
    r"sync\s+this\s+thread\s+to\s+([A-Z]+-\d+)",
    re.IGNORECASE,
)


def parse_sync_command(text: str) -> str | None:
    """Extract issue key from 'sync this thread to FILING-1234' command."""
    text = re.sub(r"<@[^>]+>\s*", "", text)
    m = _SYNC_COMMAND_RE.search(text)
    if m:
        return m.group(1).upper()
    return None


def build_sync_marker(issue_key: str) -> str:
    return f"Sync [{issue_key}]"


def thread_has_sync_marker(messages: list[dict[str, Any]], issue_key: str) -> bool:
    """Check if any message in the thread already contains Sync [ISSUE_KEY]."""
    marker = build_sync_marker(issue_key)
    for msg in messages:
        text = msg.get("text", "")
        if marker in text:
            return True
    return False


def jira_has_thread_comment(
    comments: list[dict[str, Any]],
    thread_ts: str,
) -> bool:
    """Check if any Jira comment already references this thread_ts."""
    for comment in comments:
        body_text = _extract_comment_text(comment)
        if thread_ts in body_text:
            return True
    return False


def _extract_comment_text(comment: dict[str, Any]) -> str:
    """Extract plain text from a Jira ADF comment body."""
    body = comment.get("body", {})
    if isinstance(body, str):
        return body
    parts: list[str] = []
    for block in body.get("content", []):
        for inline in block.get("content", []):
            if inline.get("type") == "text":
                parts.append(inline.get("text", ""))
    return " ".join(parts)


def build_jira_comment_body(
    *,
    channel: str,
    thread_ts: str,
    permalink: str | None = None,
    transcript: str,
) -> str:
    """Build the text content for a Jira comment linking back to Slack."""
    lines = [
        f"Slack channel: {channel}",
        f"Thread timestamp: {thread_ts}",
    ]
    if permalink:
        lines.append(f"Slack permalink: {permalink}")
    lines.append("")
    lines.append("Thread transcript:")
    lines.append(transcript)
    return "\n".join(lines)


def build_jira_comment_adf(text: str) -> dict[str, Any]:
    """Wrap plain text into Jira ADF document format."""
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


@dataclass
class SyncResult:
    """Result of a sync operation."""

    issue_key: str
    sync_marker_posted: bool
    jira_comment_added: bool
    skipped_marker: bool = False
    skipped_comment: bool = False


class SlackClient(Protocol):
    def chat_postMessage(self, *, channel: str, text: str, thread_ts: str) -> Any: ...
    def conversations_replies(self, *, channel: str, ts: str, limit: int = 200) -> Any: ...


class JiraClient(Protocol):
    def add_comment(self, issue_key: str, text: str) -> dict[str, Any]: ...
    def get_comments(self, issue_key: str) -> list[dict[str, Any]]: ...


class SyncService:
    """Handles bidirectional Jira <-> Slack thread synchronization."""

    def __init__(self, slack: SlackClient, jira: JiraClient) -> None:
        self._slack = slack
        self._jira = jira

    def sync_after_creation(
        self,
        *,
        issue_key: str,
        channel: str,
        thread_ts: str,
        permalink: str | None = None,
        transcript: str,
    ) -> SyncResult:
        """Post-creation sync: Slack marker + Jira comment, with dedup."""
        return self._do_sync(
            issue_key=issue_key,
            channel=channel,
            thread_ts=thread_ts,
            permalink=permalink,
            transcript=transcript,
        )

    def sync_existing(
        self,
        *,
        issue_key: str,
        channel: str,
        thread_ts: str,
        permalink: str | None = None,
        transcript: str,
    ) -> SyncResult:
        """Sync-only command: add Slack context to existing Jira issue, no new issue."""
        return self._do_sync(
            issue_key=issue_key,
            channel=channel,
            thread_ts=thread_ts,
            permalink=permalink,
            transcript=transcript,
        )

    def _do_sync(
        self,
        *,
        issue_key: str,
        channel: str,
        thread_ts: str,
        permalink: str | None,
        transcript: str,
    ) -> SyncResult:
        marker_posted = False
        comment_added = False
        skipped_marker = False
        skipped_comment = False

        try:
            resp = self._slack.conversations_replies(channel=channel, ts=thread_ts, limit=200)
            existing_msgs = resp.get("messages", []) if isinstance(resp, dict) else []
        except Exception:
            existing_msgs = []

        marker = build_sync_marker(issue_key)
        if thread_has_sync_marker(existing_msgs, issue_key):
            skipped_marker = True
        else:
            try:
                self._slack.chat_postMessage(
                    channel=channel,
                    text=marker,
                    thread_ts=thread_ts,
                )
                marker_posted = True
            except Exception:
                logger.exception("Failed to post sync marker to Slack")

        try:
            existing_comments = self._jira.get_comments(issue_key)
        except Exception:
            existing_comments = []

        if jira_has_thread_comment(existing_comments, thread_ts):
            skipped_comment = True
        else:
            comment_text = build_jira_comment_body(
                channel=channel,
                thread_ts=thread_ts,
                permalink=permalink,
                transcript=transcript,
            )
            try:
                self._jira.add_comment(issue_key, comment_text)
                comment_added = True
            except Exception:
                logger.exception("Failed to add Jira comment")

        return SyncResult(
            issue_key=issue_key,
            sync_marker_posted=marker_posted,
            jira_comment_added=comment_added,
            skipped_marker=skipped_marker,
            skipped_comment=skipped_comment,
        )
