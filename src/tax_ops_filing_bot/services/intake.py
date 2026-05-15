"""IntakeService: filters messages, calls LLM, applies mapping, produces a FilingIssueDraft.

Due date source of truth (in order):
  1. Matched child filing ticket's duedate field
  2. Explicit date from thread text (validated against raw thread)
  3. If neither, leave due_date blank and set needs_mapping_review = true
"""

from __future__ import annotations

import re
import logging
from datetime import date
from typing import Any, Protocol, Sequence

from tax_ops_filing_bot.llm.prompts import SYSTEM_PROMPT, build_messages
from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    IssueType,
    LLMExtraction,
    ThreadMessage,
)
from tax_ops_filing_bot.services.filing_reference import EpicChildIssue, enrich_draft_with_epic_children
from tax_ops_filing_bot.services.mapping import apply_mapping, compute_blocker_sla
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


_DATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b"),
    re.compile(
        r"\b(january|february|march|april|may|june|july|august|september|"
        r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|"
        r"oct|nov|dec)\s+(\d{1,2}),?\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(\d{1,2})/(\d{1,2})\b"),
]


def parse_iso_date(raw: str | None) -> date | None:
    """Parse YYYY-MM-DD from LLM output; ignores trailing time if present."""
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def validate_date_in_thread(d: date, thread_text: str) -> bool:
    """Check that a date plausibly appears in the thread text.

    Looks for common date representations: ISO format, MM/DD/YYYY, MM/DD,
    month-day-year strings, and partial matches like the month+day or
    just day/month numbers adjacent to year.
    """
    iso_str = d.isoformat()
    if iso_str in thread_text:
        return True

    m, day, y = d.month, d.day, d.year
    slash_full = f"{m}/{day}/{y}"
    slash_short = f"{m}/{day}/{y % 100:02d}"
    slash_no_year = f"{m}/{day}"
    padded = f"{m:02d}/{day:02d}"

    for fmt in (slash_full, slash_short, slash_no_year, padded):
        if fmt in thread_text:
            return True

    month_names = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]
    month_abbrs = [
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec",
    ]
    lower = thread_text.lower()
    name = month_names[m - 1]
    abbr = month_abbrs[m - 1]
    if re.search(rf"\b{name}\s+{day}\b", lower):
        return True
    if re.search(rf"\b{abbr}\s+{day}\b", lower):
        return True

    return False


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
        lines: list[str] = []
        for msg in messages:
            lines.append(f"[{msg.timestamp}] {msg.author}: {msg.text}")
        return "\n".join(lines)

    def create_draft(
        self,
        messages: list[ThreadMessage],
        *,
        channel: str = "unknown",
        thread_ts: str | None = None,
        epic_child_issues: Sequence[EpicChildIssue] | None = None,
        today: date | None = None,
    ) -> FilingIssueDraft:
        """Produce a FilingIssueDraft from thread messages.

        Due date source of truth:
          1. Matched child filing ticket (from epic_child_issues)
          2. Validated explicit date from thread text
          3. If neither, leave blank + needs_mapping_review
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

        today_eff = today or date.today()

        llm_due_date = parse_iso_date(extraction.due_date)
        validated_thread_date: date | None = None
        if llm_due_date and validate_date_in_thread(llm_due_date, thread_text):
            validated_thread_date = llm_due_date

        mapping = apply_mapping(
            description=extraction.description,
            tax_period=extraction.tax_period,
            impact_hint=extraction.impact_scope,
            due_date=None,
            today=today_eff,
        )

        sanitized_description = _sanitize_description(extraction.description)

        draft = FilingIssueDraft(
            summary=extraction.summary,
            description=sanitized_description,
            issue_type=mapping.issue_type,
            labels=mapping.labels,
            parent_epic_key=mapping.parent_epic_key,
            due_date=None,
            related_filing_issue_keys=[],
            filing_period=mapping.filing_period,
            year=mapping.year,
            sla_priority=mapping.sla_priority,
            sla_tracker=mapping.sla_tracker,
            sla_status=mapping.sla_status,
            filing_frequency=mapping.filing_frequency,
            ff_client_id=extraction.ff_client_id,
            impact=mapping.impact,
            state=extraction.state,
            filing_unit_code=extraction.filing_code,
            company_name=extraction.client_or_entity,
            source_channel=channel,
            source_thread_ts=thread_ts,
            reporter=extraction.reporter,
            confidence=extraction.confidence,
            needs_mapping_review=mapping.needs_mapping_review,
        )

        if epic_child_issues:
            draft = enrich_draft_with_epic_children(draft, epic_child_issues)

        if draft.due_date is None and validated_thread_date:
            draft = draft.model_copy(update={"due_date": validated_thread_date.isoformat()})

        if draft.due_date is not None and draft.issue_type == IssueType.BLOCKER:
            due = parse_iso_date(draft.due_date)
            if due:
                p, t, s = compute_blocker_sla(due, today_eff)
                draft = draft.model_copy(update={
                    "sla_priority": p,
                    "sla_tracker": t,
                    "sla_status": s,
                })

        if draft.issue_type == IssueType.BLOCKER and draft.due_date is None:
            draft = draft.model_copy(update={"needs_mapping_review": True})

        return draft
