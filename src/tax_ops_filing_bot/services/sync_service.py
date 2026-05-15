"""Persistent two-way Jira <-> Slack thread synchronization.

Architecture:
  - SyncLink stores metadata for each linked Slack thread / Jira issue pair
  - SyncLinkStore is a pluggable persistence layer (in-memory default)
  - SyncService orchestrates all sync operations

Initial link (after ticket creation or sync-only command):
  1. Post ``Sync [FILING-KEY]`` into the Slack thread
  2. Add a minimal Jira comment (no channel IDs, timestamps, or audit data)
  3. Create a SyncLink for persistent two-way sync

Ongoing sync:
  - Slack reply -> Jira comment:  ``Author (Slack): message text``
  - Jira comment -> Slack reply:  ``Author (Jira): comment text``

Loop prevention:
  - Slack messages from the bot user are skipped in Slack->Jira direction
  - Jira comments containing ``[synced-from-slack]`` are skipped in Jira->Slack
  - The initial link comment is also skipped in Jira->Slack

Deduplication:
  - Sync markers checked before posting
  - Link comments checked before adding
  - ``last_synced_slack_ts`` and ``last_synced_jira_comment_id`` in SyncLink
    prevent reprocessing old messages
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

logger = logging.getLogger(__name__)

_SYNC_MARKER_RE = re.compile(r"Sync\s+\[([A-Z]+-\d+)\]")
_SYNC_COMMAND_RE = re.compile(
    r"sync\s+this\s+thread\s+to\s+([A-Z]+-\d+)",
    re.IGNORECASE,
)

LINK_COMMENT_MARKER = "Linked Slack thread for ongoing discussion and updates."
SYNCED_FROM_SLACK_MARKER = "[synced-from-slack]"


def build_initial_link_comment(permalink: str | None = None) -> str:
    """Build the initial Jira link comment with the Slack permalink."""
    if permalink:
        return f"Linked Slack thread: {permalink}\n{LINK_COMMENT_MARKER}"
    return f"Linked Slack thread:\n{LINK_COMMENT_MARKER}"


# ---------------------------------------------------------------------------
# Sync metadata
# ---------------------------------------------------------------------------

@dataclass
class SyncLink:
    """Metadata for a linked Slack thread <-> Jira issue pair."""

    issue_key: str
    channel_id: str
    thread_ts: str
    permalink: str | None = None
    last_synced_slack_ts: str | None = None
    last_synced_jira_comment_id: str | None = None


class SyncLinkStore(Protocol):
    """Pluggable persistence for sync links."""

    def get_by_issue(self, issue_key: str) -> SyncLink | None: ...
    def get_by_thread(self, channel_id: str, thread_ts: str) -> SyncLink | None: ...
    def save(self, link: SyncLink) -> None: ...


class InMemorySyncLinkStore:
    """In-memory store for testing and development."""

    def __init__(self) -> None:
        self._by_issue: dict[str, SyncLink] = {}
        self._by_thread: dict[tuple[str, str], SyncLink] = {}

    def get_by_issue(self, issue_key: str) -> SyncLink | None:
        return self._by_issue.get(issue_key)

    def get_by_thread(self, channel_id: str, thread_ts: str) -> SyncLink | None:
        return self._by_thread.get((channel_id, thread_ts))

    def save(self, link: SyncLink) -> None:
        self._by_issue[link.issue_key] = link
        self._by_thread[(link.channel_id, link.thread_ts)] = link

    @property
    def links(self) -> list[SyncLink]:
        return list(self._by_issue.values())


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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


def jira_has_link_comment(comments: list[dict[str, Any]]) -> bool:
    """Check if any Jira comment contains the initial link marker."""
    for comment in comments:
        body_text = _extract_comment_text(comment)
        if LINK_COMMENT_MARKER in body_text:
            return True
    return False


def jira_has_thread_comment(
    comments: list[dict[str, Any]],
    thread_ts: str,
) -> bool:
    """Check if any Jira comment already references this thread_ts.

    Kept for backward compatibility; new code uses jira_has_link_comment.
    """
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


def _is_synced_from_slack(comment: dict[str, Any]) -> bool:
    """True if the Jira comment was created by the Slack->Jira sync engine."""
    text = _extract_comment_text(comment)
    return SYNCED_FROM_SLACK_MARKER in text


def _is_initial_link_comment(comment: dict[str, Any]) -> bool:
    """True if the Jira comment is the initial link comment."""
    text = _extract_comment_text(comment)
    return LINK_COMMENT_MARKER in text


def build_slack_to_jira_comment(author: str, text: str) -> str:
    """Format a Slack message as a Jira comment for sync."""
    return f"{author} (Slack): {text}\n{SYNCED_FROM_SLACK_MARKER}"


def build_jira_to_slack_message(author: str, text: str) -> str:
    """Format a Jira comment as a Slack message for sync."""
    return f"{author} (Jira): {text}"


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


def _get_jira_comment_id(comment: dict[str, Any]) -> str | None:
    """Extract the comment ID from a Jira comment dict."""
    return comment.get("id")


def _get_jira_comment_author(comment: dict[str, Any]) -> str:
    """Extract author display name from a Jira comment."""
    author = comment.get("author", {})
    return author.get("displayName", "Unknown")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    """Result of an initial link / sync-only operation."""

    issue_key: str
    sync_marker_posted: bool
    jira_comment_added: bool
    skipped_marker: bool = False
    skipped_comment: bool = False


@dataclass
class ContinuousSyncResult:
    """Result of ongoing two-way sync."""

    issue_key: str
    slack_to_jira_synced: int = 0
    jira_to_slack_synced: int = 0
    slack_to_jira_skipped: int = 0
    jira_to_slack_skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Client protocols
# ---------------------------------------------------------------------------

class SlackClient(Protocol):
    def chat_postMessage(self, *, channel: str, text: str, thread_ts: str) -> Any: ...
    def conversations_replies(self, *, channel: str, ts: str, limit: int = 200) -> Any: ...


class JiraClient(Protocol):
    def add_comment(self, issue_key: str, text: str) -> dict[str, Any]: ...
    def get_comments(self, issue_key: str) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# SyncService
# ---------------------------------------------------------------------------

class SyncService:
    """Persistent two-way Jira <-> Slack thread synchronization."""

    def __init__(
        self,
        slack: SlackClient,
        jira: JiraClient,
        store: SyncLinkStore | None = None,
        *,
        bot_user_id: str | None = None,
    ) -> None:
        self._slack = slack
        self._jira = jira
        self._store: SyncLinkStore = store or InMemorySyncLinkStore()
        self._bot_user_id = bot_user_id

    # -- Initial link / sync-only command ----------------------------------

    def sync_after_creation(
        self,
        *,
        issue_key: str,
        channel: str,
        thread_ts: str,
        permalink: str | None = None,
        transcript: str = "",
    ) -> SyncResult:
        """Post-creation sync: Slack marker + minimal Jira comment + create link."""
        return self._establish_link(
            issue_key=issue_key,
            channel=channel,
            thread_ts=thread_ts,
            permalink=permalink,
        )

    def sync_existing(
        self,
        *,
        issue_key: str,
        channel: str,
        thread_ts: str,
        permalink: str | None = None,
        transcript: str = "",
    ) -> SyncResult:
        """Sync-only command: link to existing Jira issue, no new issue created."""
        return self._establish_link(
            issue_key=issue_key,
            channel=channel,
            thread_ts=thread_ts,
            permalink=permalink,
        )

    def _establish_link(
        self,
        *,
        issue_key: str,
        channel: str,
        thread_ts: str,
        permalink: str | None,
    ) -> SyncResult:
        """Create the bidirectional link between a Slack thread and Jira issue."""
        marker_posted = False
        comment_added = False
        skipped_marker = False
        skipped_comment = False

        try:
            resp = self._slack.conversations_replies(
                channel=channel, ts=thread_ts, limit=200,
            )
            existing_msgs = resp.get("messages", []) if isinstance(resp, dict) else []
        except Exception:
            existing_msgs = []

        if thread_has_sync_marker(existing_msgs, issue_key):
            skipped_marker = True
        else:
            try:
                self._slack.chat_postMessage(
                    channel=channel,
                    text=build_sync_marker(issue_key),
                    thread_ts=thread_ts,
                )
                marker_posted = True
            except Exception:
                logger.exception("Failed to post sync marker to Slack")

        try:
            existing_comments = self._jira.get_comments(issue_key)
        except Exception:
            existing_comments = []

        if jira_has_link_comment(existing_comments):
            skipped_comment = True
        else:
            try:
                self._jira.add_comment(
                    issue_key, build_initial_link_comment(permalink),
                )
                comment_added = True
            except Exception:
                logger.exception("Failed to add initial Jira link comment")

        last_slack_ts = thread_ts
        if existing_msgs:
            last_slack_ts = max(
                (m.get("ts", thread_ts) for m in existing_msgs),
                default=thread_ts,
            )

        last_jira_id: str | None = None
        all_comments = existing_comments
        if comment_added:
            try:
                all_comments = self._jira.get_comments(issue_key)
            except Exception:
                pass
        if all_comments:
            ids = [_get_jira_comment_id(c) for c in all_comments if _get_jira_comment_id(c)]
            if ids:
                last_jira_id = ids[-1]

        link = SyncLink(
            issue_key=issue_key,
            channel_id=channel,
            thread_ts=thread_ts,
            permalink=permalink,
            last_synced_slack_ts=last_slack_ts,
            last_synced_jira_comment_id=last_jira_id,
        )
        self._store.save(link)

        return SyncResult(
            issue_key=issue_key,
            sync_marker_posted=marker_posted,
            jira_comment_added=comment_added,
            skipped_marker=skipped_marker,
            skipped_comment=skipped_comment,
        )

    # -- Continuous two-way sync -------------------------------------------

    def sync_slack_to_jira(
        self,
        issue_key: str | None = None,
        link: SyncLink | None = None,
    ) -> ContinuousSyncResult:
        """Sync new Slack thread replies to Jira comments.

        Skips messages from the bot user (loop prevention) and messages
        already synced (deduplication via last_synced_slack_ts).
        """
        if link is None:
            if issue_key is None:
                raise ValueError("Must provide issue_key or link")
            link = self._store.get_by_issue(issue_key)
        if link is None:
            return ContinuousSyncResult(issue_key=issue_key or "", errors=["No sync link found"])

        result = ContinuousSyncResult(issue_key=link.issue_key)

        try:
            resp = self._slack.conversations_replies(
                channel=link.channel_id, ts=link.thread_ts, limit=200,
            )
            messages = resp.get("messages", []) if isinstance(resp, dict) else []
        except Exception as e:
            result.errors.append(f"Failed to fetch Slack replies: {e}")
            return result

        new_messages = self._filter_new_slack_messages(messages, link)

        for msg in new_messages:
            user = msg.get("user", "")
            if self._bot_user_id and user == self._bot_user_id:
                result.slack_to_jira_skipped += 1
                continue

            text = msg.get("text", "")
            if _SYNC_MARKER_RE.search(text):
                result.slack_to_jira_skipped += 1
                continue

            author = msg.get("user_profile", {}).get("real_name") or msg.get("username") or user
            comment_text = build_slack_to_jira_comment(author, text)

            try:
                self._jira.add_comment(link.issue_key, comment_text)
                result.slack_to_jira_synced += 1
            except Exception as e:
                result.errors.append(f"Failed to add Jira comment for Slack ts={msg.get('ts')}: {e}")

        if new_messages:
            link.last_synced_slack_ts = new_messages[-1].get("ts", link.last_synced_slack_ts)
            self._store.save(link)

        return result

    def sync_jira_to_slack(
        self,
        issue_key: str | None = None,
        link: SyncLink | None = None,
    ) -> ContinuousSyncResult:
        """Sync new Jira comments to Slack thread replies.

        Skips comments that were synced from Slack (loop prevention),
        the initial link comment, and already-synced comments.
        """
        if link is None:
            if issue_key is None:
                raise ValueError("Must provide issue_key or link")
            link = self._store.get_by_issue(issue_key)
        if link is None:
            return ContinuousSyncResult(issue_key=issue_key or "", errors=["No sync link found"])

        result = ContinuousSyncResult(issue_key=link.issue_key)

        try:
            comments = self._jira.get_comments(link.issue_key)
        except Exception as e:
            result.errors.append(f"Failed to fetch Jira comments: {e}")
            return result

        new_comments = self._filter_new_jira_comments(comments, link)

        for comment in new_comments:
            if _is_synced_from_slack(comment):
                result.jira_to_slack_skipped += 1
                continue

            if _is_initial_link_comment(comment):
                result.jira_to_slack_skipped += 1
                continue

            author = _get_jira_comment_author(comment)
            text = _extract_comment_text(comment)
            slack_msg = build_jira_to_slack_message(author, text)

            try:
                self._slack.chat_postMessage(
                    channel=link.channel_id,
                    text=slack_msg,
                    thread_ts=link.thread_ts,
                )
                result.jira_to_slack_synced += 1
            except Exception as e:
                cid = _get_jira_comment_id(comment)
                result.errors.append(f"Failed to post to Slack for Jira comment id={cid}: {e}")

        if new_comments:
            last_id = _get_jira_comment_id(new_comments[-1])
            if last_id:
                link.last_synced_jira_comment_id = last_id
                self._store.save(link)

        return result

    def sync_all(
        self,
        issue_key: str | None = None,
        link: SyncLink | None = None,
    ) -> tuple[ContinuousSyncResult, ContinuousSyncResult]:
        """Run both directions of sync and return (slack_to_jira, jira_to_slack)."""
        if link is None and issue_key:
            link = self._store.get_by_issue(issue_key)
        s2j = self.sync_slack_to_jira(link=link)
        j2s = self.sync_jira_to_slack(link=link)
        return s2j, j2s

    # -- Private helpers ---------------------------------------------------

    def _filter_new_slack_messages(
        self,
        messages: Sequence[dict[str, Any]],
        link: SyncLink,
    ) -> list[dict[str, Any]]:
        """Return messages newer than the last synced timestamp."""
        if not link.last_synced_slack_ts:
            return list(messages)
        cutoff = link.last_synced_slack_ts
        return [m for m in messages if m.get("ts", "0") > cutoff]

    def _filter_new_jira_comments(
        self,
        comments: Sequence[dict[str, Any]],
        link: SyncLink,
    ) -> list[dict[str, Any]]:
        """Return comments with IDs after the last synced comment ID."""
        if not link.last_synced_jira_comment_id:
            return list(comments)
        cutoff = link.last_synced_jira_comment_id
        found_cutoff = False
        result: list[dict[str, Any]] = []
        for c in comments:
            cid = _get_jira_comment_id(c)
            if cid == cutoff:
                found_cutoff = True
                continue
            if found_cutoff:
                result.append(c)
        return result

    def get_link(self, issue_key: str) -> SyncLink | None:
        """Look up an existing sync link by issue key."""
        return self._store.get_by_issue(issue_key)

    def get_link_by_thread(self, channel_id: str, thread_ts: str) -> SyncLink | None:
        """Look up an existing sync link by Slack thread."""
        return self._store.get_by_thread(channel_id, thread_ts)
