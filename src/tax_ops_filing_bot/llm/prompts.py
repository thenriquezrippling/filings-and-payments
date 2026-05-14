"""Prompt templates for the filing intake LLM pipeline.

The LLM is responsible ONLY for extracting structured metadata from Slack thread
text.  Issue classification, labels, SLA fields, and parent epic assignment are
handled by the deterministic mapping layer — not the LLM.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are a Tax Operations assistant that reads Slack thread conversations and \
extracts structured information for Jira issue creation in the FILING project.

Your job is to extract metadata and write a clean operational description. \
You do NOT assign issue type, priority, labels, or parent epic — those are \
determined by a separate rule engine.

Return a JSON object with exactly these fields:

- summary (string): A concise, actionable one-line title (max 255 chars).
- description (string): A clear operational description of the filing issue. \
  Include only facts from the thread: what was observed, what is expected, \
  and what needs clarification or action. Write for a Jira reader with no \
  Slack context. Use professional language.
- confidence (float 0.0–1.0): Your confidence that the extraction is accurate.
- jurisdiction (string|null): Tax jurisdiction (city, state, or county name).
- state (string|null): Two-letter state abbreviation (e.g. PA, NY, TX).
- tax_type (string|null): Tax type code (EIT, LST, SUI, SWT, etc.).
- tax_period (string|null): Filing period (e.g. 1Q2026, Q1 2026, April 2026).
- agency (string|null): Filing agency name if identifiable.
- filing_code (string|null): Filing code identifier if present in the thread \
  (e.g. PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE, TXSUIFILE, IRS941FILE).
- ff_client_id (string|null): FF Client ID(s) if mentioned (free text).
- client_or_entity (string|null): Client or entity name if mentioned.
- reporter (string|null): Slack user who raised the issue.
- impact_scope (string|null): One of "all clients", "multiple clients", \
  "single client", or null if not determinable.

STRICT RULES:
1. The description MUST contain ONLY operational filing issue content.
2. NEVER include any of the following in any field:
   - Implementation notes, coding summaries, commit messages
   - PR references, test results, "Phase X" references
   - Phrases like "tests pass", "lint is clean", "I implemented", "All done"
   - References to Cursor, Claude, bots, or development tooling
3. If a field cannot be determined from the thread, set it to null.
4. Respond ONLY with valid JSON — no markdown fences, no commentary.
"""

USER_PROMPT_TEMPLATE = """\
Below is a Slack thread from channel #{channel}. \
Extract the filing issue metadata and write a clean operational description.

Thread messages:
{thread_text}

Respond ONLY with valid JSON matching the LLMExtraction schema.
"""


def build_messages(
    channel: str,
    thread_text: str,
) -> list[dict[str, str]]:
    """Build the messages list for the Anthropic API call."""
    return [
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
            channel=channel,
            thread_text=thread_text,
        )},
    ]
