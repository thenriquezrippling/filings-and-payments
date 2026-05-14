"""Parse bot commands from Slack mention text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_SYNC_RE = re.compile(
    r"sync\s+this\s+thread\s+to\s+(?P<issue_key>[A-Z][A-Z0-9_]+-\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SyncCommand:
    """Parsed ``sync this thread to FILING-1234`` command."""

    issue_key: str


def parse_sync_command(text: str) -> Optional[SyncCommand]:
    """Return a ``SyncCommand`` if the text matches, else ``None``.

    The bot mention prefix (e.g. ``<@U123>``) is stripped automatically.
    """
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    m = _SYNC_RE.search(cleaned)
    if m:
        return SyncCommand(issue_key=m.group("issue_key").upper())
    return None
