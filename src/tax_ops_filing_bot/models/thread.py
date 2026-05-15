"""Slack thread message models and normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ThreadMessage(BaseModel):
    """A single message from a Slack thread, already resolved to display names."""

    user_id: str
    username: str = "unknown"
    text: str
    ts: str = Field(description="Slack message timestamp (e.g. '1715000000.000100')")

    @property
    def datetime_utc(self) -> datetime:
        epoch = float(self.ts.split(".")[0])
        return datetime.fromtimestamp(epoch, tz=timezone.utc)


class NormalizedThread(BaseModel):
    """A fully-resolved Slack thread ready for LLM consumption."""

    channel_id: str
    thread_ts: str
    messages: list[ThreadMessage] = Field(default_factory=list)
    permalink: Optional[str] = None

    @property
    def plain_text(self) -> str:
        """Render the thread as a plain-text transcript for the LLM prompt."""
        lines: list[str] = []
        for msg in self.messages:
            lines.append(f"[{msg.username}] {msg.text}")
        return "\n".join(lines)

    @property
    def message_count(self) -> int:
        return len(self.messages)
