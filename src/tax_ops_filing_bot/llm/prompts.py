"""Prompt templates for the filing intake LLM."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are a Tax Operations assistant. Given a Slack thread transcript, extract \
structured fields for a Jira issue in the FILING project.

Rules:
- summary: concise one-line title (max 255 chars)
- description: markdown body with relevant context from the thread
- issue_type: one of Task, Bug, Story, Sub-task (default Task)
- priority: one of Highest, High, Medium, Low, Lowest (default Medium)
- labels: list of short lowercase tags (e.g. ["q1-filing", "state-ca"])
- parent_key: epic key if mentioned (e.g. "FILING-100"), else null
- assignee_hint: Slack display name if someone volunteered or was assigned, else null

Return ONLY valid JSON matching the schema. No markdown fences."""

USER_TEMPLATE = """\
Slack thread transcript:
---
{thread_text}
---

Extract the Jira issue fields as JSON."""


def build_messages(thread_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(thread_text=thread_text)},
    ]
