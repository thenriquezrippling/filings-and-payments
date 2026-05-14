"""CLI entry point for generating a FilingIssueDraft from thread text."""

from __future__ import annotations

import json
import logging
import os
import sys

from dotenv import load_dotenv

from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.filing import ThreadMessage
from tax_ops_filing_bot.services.intake import IntakeService

logger = logging.getLogger(__name__)


def draft_from_thread() -> None:
    """Read thread messages from stdin (JSON list) or args, call LLM, print draft."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    channel = os.environ.get("SLACK_CHANNEL", "unknown")

    if not sys.stdin.isatty():
        raw = sys.stdin.read()
    elif len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        logger.error("Provide thread messages as JSON on stdin or as first argument")
        sys.exit(1)

    raw_messages = json.loads(raw)
    messages = [ThreadMessage.model_validate(m) for m in raw_messages]

    client = AnthropicClient(api_key=api_key)
    service = IntakeService(client)
    draft = service.create_draft(messages, channel=channel)

    print(json.dumps(draft.model_dump(), indent=2))
