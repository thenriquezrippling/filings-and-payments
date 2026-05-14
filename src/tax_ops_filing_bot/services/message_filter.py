"""Filter bot-generated and development-chatter messages from Slack threads."""

from __future__ import annotations

import re

from tax_ops_filing_bot.models.filing import ThreadMessage

BOT_AUTHORS: frozenset[str] = frozenset({
    "cursor",
    "claude",
    "claude-filings",
    "slackbot",
    "github",
    "github-actions",
    "jira",
    "atlassian",
})

DEV_CHATTER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\btests?\s+pass",
        r"\blint\s+is\s+clean\b",
        r"\bI\s+implemented\b",
        r"\bcommit\b",
        r"\b(pull\s+request|PR\s*#?\d+)\b",
        r"\bPhase\s+\d",
        r"\bAll\s+done\b",
        r"\bHere'?s\s+what\s+I\s+implemented\b",
        r"\bruff\b.*\bcheck",
        r"\bpytest\b",
        r"\bpip\s+install\b",
        r"\bgit\s+(push|add|status)\b",
        r"\bmerge\s+(branch|conflict)\b",
    ]
]


def is_bot_message(msg: ThreadMessage) -> bool:
    """Return True if the message is from a known bot author."""
    if msg.is_bot:
        return True
    return msg.author.strip().lower() in BOT_AUTHORS


def is_dev_chatter(msg: ThreadMessage) -> bool:
    """Return True if the message contains development/implementation noise."""
    return any(pat.search(msg.text) for pat in DEV_CHATTER_PATTERNS)


def filter_messages(messages: list[ThreadMessage]) -> list[ThreadMessage]:
    """Return only human, operationally-relevant messages."""
    return [
        msg
        for msg in messages
        if not is_bot_message(msg) and not is_dev_chatter(msg)
    ]
