"""IntakeService: orchestrates thread → LLM inference → draft for confirmation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tax_ops_filing_bot.llm.prompts import build_messages
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.issue_draft import (
    FilingIssueDraft,
    classify_work_type,
    generate_labels,
    resolve_parent_epic,
)
from tax_ops_filing_bot.models.thread import NormalizedThread

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    draft: FilingIssueDraft
    thread: NormalizedThread


class IntakeService:
    """Turn a normalized Slack thread into a ``FilingIssueDraft``."""

    def __init__(self, llm: AnthropicClient) -> None:
        self._llm = llm

    def infer_draft(self, thread: NormalizedThread) -> IntakeResult:
        """Run the LLM (or mock) to produce a draft from the thread transcript.

        After LLM inference, deterministic post-processing is applied:
        - Work type classification from thread text
        - Parent epic resolution from keyword matching
        - Label generation from thread content
        """
        plain_text = thread.plain_text
        messages = build_messages(plain_text)
        draft = self._llm.complete_json(messages, FilingIssueDraft)

        draft.issue_type = classify_work_type(plain_text)

        epic = resolve_parent_epic(plain_text)
        if epic:
            draft.parent_key = epic

        generated_labels = generate_labels(plain_text)
        if generated_labels:
            existing = set(draft.labels)
            draft.labels = sorted(existing | set(generated_labels))

        logger.info("Inferred draft: %s [type=%s, epic=%s]", draft.summary, draft.issue_type.value, draft.parent_key)
        return IntakeResult(draft=draft, thread=thread)
