"""IntakeService: orchestrates thread → LLM inference → draft for confirmation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tax_ops_filing_bot.llm.prompts import build_messages
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft
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
        """Run the LLM (or mock) to produce a draft from the thread transcript."""
        messages = build_messages(thread.plain_text)
        draft = self._llm.complete_json(messages, FilingIssueDraft)
        logger.info("Inferred draft: %s", draft.summary)
        return IntakeResult(draft=draft, thread=thread)
