"""IntakeService: filters messages, calls LLM, applies mapping, produces a FilingIssueDraft."""

from __future__ import annotations

import re
import logging
from typing import Any, Protocol

from tax_ops_filing_bot.llm.prompts import SYSTEM_PROMPT, build_messages
from tax_ops_filing_bot.models.filing import FilingIssueDraft, LLMExtraction, ThreadMessage
from tax_ops_filing_bot.services.mapping import apply_mapping
from tax_ops_filing_bot.services.message_filter import filter_messages

logger = logging.getLogger(__name__)

DESCRIPTION_BLACKLIST_PATTERNS: list[re.Pattern[str]] = [
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
        r"\bruff\b",
        r"\bpytest\b",
        r"\bpip\s+install\b",
        r"\bgit\s+(push|add|status|commit)\b",
        r"\bCursor\b",
        r"\bClaude\b",
        r"\bbot[\s-]generated\b",
    ]
]


def _sanitize_description(description: str) -> str:
    """Remove any implementation/dev noise that leaked through the LLM."""
    lines = description.split("\n")
    clean_lines: list[str] = []
    for line in lines:
        if any(pat.search(line) for pat in DESCRIPTION_BLACKLIST_PATTERNS):
            continue
        clean_lines.append(line)

    result = "\n".join(clean_lines).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


class LLMClient(Protocol):
    """Protocol for any LLM client that can produce structured output."""

    def complete_json(
        self,
        messages: list[dict[str, Any]],
        response_model: type,
        *,
        system: str | None = None,
    ) -> Any: ...


class IntakeService:
    """Orchestrates draft creation: filter -> LLM extract -> deterministic map."""

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
        """Produce a FilingIssueDraft from thread messages.

        Pipeline:
        1. Filter out bot/dev-chatter messages
        2. Send clean thread text to LLM for extraction
        3. Apply deterministic mapping for issue_type, labels, SLA fields, etc.
        4. Sanitize description to remove any leaked implementation noise
        """
        clean_messages = filter_messages(messages)
        if not clean_messages:
            clean_messages = messages
            logger.warning("All messages filtered out — falling back to unfiltered")

        thread_text = self.format_thread(clean_messages)
        llm_messages = build_messages(channel=channel, thread_text=thread_text)

        extraction: LLMExtraction = self._llm.complete_json(
            llm_messages,
            LLMExtraction,
            system=SYSTEM_PROMPT,
        )

        mapping = apply_mapping(
            description=extraction.description,
            tax_period=extraction.tax_period,
            impact_hint=extraction.impact_scope,
        )

        sanitized_description = _sanitize_description(extraction.description)

        return FilingIssueDraft(
            summary=extraction.summary,
            description=sanitized_description,
            issue_type=mapping.issue_type,
            labels=mapping.labels,
            parent_epic_key=mapping.parent_epic_key,
            filing_period=mapping.filing_period,
            year=mapping.year,
            sla_priority=mapping.sla_priority,
            sla_tracker=mapping.sla_tracker,
            filing_frequency=mapping.filing_frequency,
            ff_client_id=extraction.ff_client_id,
            impact=mapping.impact,
            state=extraction.state,
            filing_unit_code=extraction.filing_code,
            company_name=extraction.client_or_entity,
            source_channel=channel,
            source_thread_ts=None,
            reporter=extraction.reporter,
            confidence=extraction.confidence,
            needs_mapping_review=mapping.needs_mapping_review,
        )
