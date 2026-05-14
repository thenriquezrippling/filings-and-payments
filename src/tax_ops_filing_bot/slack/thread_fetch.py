"""Utilities for fetching and parsing Slack thread messages."""

from __future__ import annotations

import logging
import re
from typing import Any

from slack_sdk import WebClient

from tax_ops_filing_bot.models.schemas import ThreadContext, ThreadMessage

logger = logging.getLogger(__name__)

_SYNC_PATTERN = re.compile(
    r"sync\s+this\s+thread\s+to\s+([A-Z]+-\d+)",
    re.IGNORECASE,
)


def fetch_thread(
    client: WebClient,
    channel_id: str,
    thread_ts: str,
) -> ThreadContext:
    """Fetch all messages in a thread and return a ``ThreadContext``."""
    result = client.conversations_replies(
        channel=channel_id,
        ts=thread_ts,
        limit=200,
    )
    raw_messages: list[dict[str, Any]] = result.get("messages", [])
    messages = [
        ThreadMessage(
            user=msg.get("user", "unknown"),
            text=msg.get("text", ""),
            ts=msg["ts"],
        )
        for msg in raw_messages
    ]

    permalink: str | None = None
    try:
        link_resp = client.chat_getPermalink(
            channel=channel_id,
            message_ts=thread_ts,
        )
        permalink = link_resp.get("permalink")
    except Exception:
        logger.debug("Could not get permalink for %s/%s", channel_id, thread_ts)

    return ThreadContext(
        channel_id=channel_id,
        thread_ts=thread_ts,
        messages=messages,
        permalink=permalink,
    )


def parse_sync_command(text: str) -> str | None:
    """Extract a Jira issue key from a 'sync this thread to FILING-XXXX' message.

    Returns the issue key string or None.
    """
    match = _SYNC_PATTERN.search(text)
    return match.group(1) if match else None
