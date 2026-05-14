"""SyncService: append thread content to an existing Jira issue as a comment."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tax_ops_filing_bot.jira.client import JiraClient
from tax_ops_filing_bot.models.thread import NormalizedThread

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    issue_key: str
    comment_id: str
    success: bool


class SyncService:
    """Sync a Slack thread's content to an existing Jira issue."""

    def __init__(self, jira: JiraClient) -> None:
        self._jira = jira

    def sync_thread(self, thread: NormalizedThread, issue_key: str) -> SyncResult:
        """Add the full thread transcript as a comment on ``issue_key``."""
        existing = self._jira.get_issue(issue_key)
        if existing is None:
            logger.error("Issue %s not found", issue_key)
            return SyncResult(issue_key=issue_key, comment_id="", success=False)

        comment_text = (
            f"*Slack thread sync* (#{thread.channel_id}, {thread.message_count} messages)\n\n"
            f"{thread.plain_text}"
        )
        result = self._jira.add_comment(issue_key, comment_text)
        comment_id = result.get("id", "")
        logger.info("Synced thread to %s (comment %s)", issue_key, comment_id)
        return SyncResult(issue_key=issue_key, comment_id=comment_id, success=True)
