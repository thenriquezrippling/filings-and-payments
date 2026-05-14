"""SyncService: append Slack thread content to an existing Jira issue."""

from __future__ import annotations

import logging
from typing import Any

from tax_ops_filing_bot.jira.client import JiraClient
from tax_ops_filing_bot.llm.prompts import format_thread_for_prompt
from tax_ops_filing_bot.models.schemas import SyncRequest

logger = logging.getLogger(__name__)


class SyncService:
    """Sync Slack thread text to an existing FILING issue as a comment."""

    def __init__(self, jira: JiraClient) -> None:
        self._jira = jira

    def sync(self, request: SyncRequest) -> dict[str, Any]:
        """Append thread messages as a formatted comment on the issue.

        Returns the Jira comment response payload.
        """
        message_dicts = [
            {"user": m.user, "text": m.text, "ts": m.ts}
            for m in request.thread.messages
        ]
        transcript = format_thread_for_prompt(message_dicts)

        header = f"Synced from Slack thread in <#{request.thread.channel_id}>"
        if request.thread.permalink:
            header += f" — [thread link]({request.thread.permalink})"

        body = f"{header}\n\n{transcript}"

        comment = self._jira.add_comment(request.issue_key, body)
        logger.info(
            "Synced %d messages to %s",
            len(request.thread.messages),
            request.issue_key,
        )
        return comment
