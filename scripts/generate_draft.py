#!/usr/bin/env python3
"""Generate a FilingIssueDraft from the Pittsburgh EIT Slack thread.

Usage:
    python scripts/generate_draft.py                   # uses mock LLM (no API key needed)
    ANTHROPIC_API_KEY=sk-... python scripts/generate_draft.py --live   # calls Anthropic
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.filing import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
    ThreadMessage,
)
from tax_ops_filing_bot.services.intake import IntakeService

THREAD_MESSAGES = [
    ThreadMessage(
        author="Tony",
        timestamp="5/14/2026, 6:37:57 AM",
        text="PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE 1Q2026",
    ),
    ThreadMessage(
        author="Tony",
        timestamp="5/14/2026, 6:38:17 AM",
        text=(
            "I am reviewing Pittsburgh EIT 0's and I wanted clarification on:\n\n"
            "-The tax year at the top of the return is showing \"ET-2025\" "
            "(This may need to be changed to 2026)\n"
            "-The Payroll Expense Tax Allocation Schedule Form is also on the "
            "second page, can we confirm if this needs to be included and if so, "
            "all the client's are showing Rippling PEO 1, Inc. as Company Name "
            "of Professional Employer Organization."
        ),
    ),
]

CHANNEL = "personal-ai-testing"


class MockLLMClient:
    """Simulates LLM inference for the Pittsburgh EIT thread."""

    def complete_json(self, messages, response_model, *, system=None):
        return FilingIssueDraft(
            summary=(
                "Pittsburgh EIT 1Q2026: Tax year showing ET-2025 instead of 2026 "
                "and PEO name defaulting to Rippling PEO 1, Inc."
            ),
            description=(
                "During review of Pittsburgh EIT returns showing $0 balances "
                "(PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE 1Q2026), two issues "
                "were identified:\n\n"
                "1. **Tax year mismatch**: The tax year at the top of the return "
                "displays \"ET-2025\" but should likely read \"ET-2026\" for the "
                "1Q2026 filing period.\n\n"
                "2. **PEO company name on Payroll Expense Tax Allocation Schedule**: "
                "The Payroll Expense Tax Allocation Schedule Form appears on the "
                "second page. All clients are showing \"Rippling PEO 1, Inc.\" as "
                "the Company Name of Professional Employer Organization. Need to "
                "confirm:\n"
                "   - Whether this form should be included in the filing\n"
                "   - Whether the PEO company name is correct or needs to reflect "
                "the actual client entity\n\n"
                "Source: Slack thread from Tony in #personal-ai-testing "
                "(5/14/2026, 6:37 AM)"
            ),
            issue_type=IssueType.BUG,
            priority=IssuePriority.HIGH,
            labels=["pittsburgh", "EIT", "payroll-expense-tax", "PEO", "1Q2026"],
            jurisdiction="City of Pittsburgh",
            tax_type="EIT",
            tax_period="1Q2026",
            client_or_entity="Rippling PEO 1, Inc.",
            source_channel=CHANNEL,
            source_thread_ts=None,
            reporter="Tony",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a FILING Jira draft")
    parser.add_argument("--live", action="store_true", help="Use live Anthropic API")
    args = parser.parse_args()

    if args.live:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
            sys.exit(1)
        llm_client = AnthropicClient(api_key=api_key)
    else:
        llm_client = MockLLMClient()

    service = IntakeService(llm_client)
    draft = service.create_draft(THREAD_MESSAGES, channel=CHANNEL)

    print(json.dumps(draft.model_dump(), indent=2))


if __name__ == "__main__":
    main()
