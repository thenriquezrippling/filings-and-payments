"""IntakeService: reads thread messages, calls LLM, produces a FilingIssueDraft."""

from __future__ import annotations

import logging
from typing import Protocol

from tax_ops_filing_bot.llm.prompts import SYSTEM_PROMPT, build_messages
from tax_ops_filing_bot.models.filing import FilingIssueDraft, ThreadMessage

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for any LLM client that can produce structured output."""

    def complete_json(
        self,
        messages: list[dict],
        response_model: type,
        *,
        system: str | None = None,
    ) -> FilingIssueDraft: ...


class IntakeService:
    """Orchestrates draft creation from Slack thread content."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    @staticmethod
    def format_thread(messages: list[ThreadMessage]) -> str:
        """Render thread messages as plain text for the LLM prompt."""
        lines: list[str] = []
        for msg in messages:
            lines.append(f"[{msg.timestamp}] {msg.author}: {msg.text}")
        return "\n".join(lines)

    def create_draft(
        self,
        messages: list[ThreadMessage],
        *,
        channel: str = "unknown",
    ) -> FilingIssueDraft:
        """Produce a FilingIssueDraft from thread messages via the LLM."""
        thread_text = self.format_thread(messages)
        llm_messages = build_messages(channel=channel, thread_text=thread_text)

        draft = self._llm.complete_json(
            llm_messages,
            FilingIssueDraft,
            system=SYSTEM_PROMPT,
        )

        if draft.source_channel is None:
            draft.source_channel = channel

        return draft
