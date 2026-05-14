"""IntakeService: orchestrate Slack thread → LLM extraction → Jira creation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tax_ops_filing_bot.jira.client import JiraClient, JiraIssue
from tax_ops_filing_bot.llm.prompts import build_extraction_messages, format_thread_for_prompt
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.schemas import FilingIssueDraft, ThreadContext

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    """Result of an intake operation."""

    draft: FilingIssueDraft
    jira_issue: JiraIssue | None = None
    confirmed: bool = False


class IntakeService:
    """Read a Slack thread, extract a FilingIssueDraft via LLM, optionally create in Jira."""

    def __init__(self, llm: AnthropicClient, jira: JiraClient) -> None:
        self._llm = llm
        self._jira = jira

    def extract_draft(self, thread: ThreadContext) -> FilingIssueDraft:
        """Run LLM extraction on a thread and return a FilingIssueDraft."""
        message_dicts = [
            {"user": m.user, "text": m.text, "ts": m.ts}
            for m in thread.messages
        ]
        transcript = format_thread_for_prompt(message_dicts)
        messages = build_extraction_messages(transcript)
        return self._llm.complete_json(messages, FilingIssueDraft)

    def create_issue(
        self,
        draft: FilingIssueDraft,
        thread: ThreadContext,
        *,
        parent_key: str | None = None,
    ) -> JiraIssue:
        """Create a Jira issue from a confirmed draft and return the issue."""
        description = draft.description
        if thread.permalink:
            description += f"\n\n---\nSlack thread: {thread.permalink}"

        issue = self._jira.create_issue(
            summary=draft.summary,
            description=description,
            priority=draft.priority,
            labels=draft.labels,
            parent_key=parent_key,
        )
        logger.info("Created %s: %s", issue.key, draft.summary)
        return issue

    def intake(
        self,
        thread: ThreadContext,
        *,
        auto_create: bool = False,
        parent_key: str | None = None,
    ) -> IntakeResult:
        """Full intake pipeline: extract draft, optionally create issue.

        When ``auto_create`` is False (default), the caller is expected to
        present the draft for user confirmation before calling
        ``create_issue`` separately.
        """
        draft = self.extract_draft(thread)
        result = IntakeResult(draft=draft)

        if auto_create:
            result.jira_issue = self.create_issue(draft, thread, parent_key=parent_key)
            result.confirmed = True

        return result
