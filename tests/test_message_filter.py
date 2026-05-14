"""Tests for message filtering (requirement F.6)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.models.filing import ThreadMessage
from tax_ops_filing_bot.services.message_filter import (
    filter_messages,
    is_bot_message,
    is_dev_chatter,
)


class TestIsBotMessage:
    def test_cursor_bot(self) -> None:
        msg = ThreadMessage(author="Cursor", timestamp="now", text="Hello")
        assert is_bot_message(msg) is True

    def test_claude_bot(self) -> None:
        msg = ThreadMessage(author="Claude", timestamp="now", text="Hello")
        assert is_bot_message(msg) is True

    def test_claude_filings_bot(self) -> None:
        msg = ThreadMessage(author="claude-filings", timestamp="now", text="Hello")
        assert is_bot_message(msg) is True

    def test_slackbot(self) -> None:
        msg = ThreadMessage(author="Slackbot", timestamp="now", text="Hello")
        assert is_bot_message(msg) is True

    def test_github_bot(self) -> None:
        msg = ThreadMessage(author="GitHub", timestamp="now", text="Hello")
        assert is_bot_message(msg) is True

    def test_is_bot_flag(self) -> None:
        msg = ThreadMessage(author="SomeApp", timestamp="now", text="Hello", is_bot=True)
        assert is_bot_message(msg) is True

    def test_human_user(self) -> None:
        msg = ThreadMessage(author="Tony", timestamp="now", text="Hello")
        assert is_bot_message(msg) is False


class TestIsDevChatter:
    @pytest.mark.parametrize("text", [
        "All tests pass!",
        "lint is clean now",
        "I implemented the fix",
        "commit abc123 pushed",
        "PR #42 is ready",
        "Phase 2 is done",
        "All done with the changes",
        "Here's what I implemented",
        "ruff check passed",
        "pytest -v ran clean",
        "pip install completed",
        "git push origin main",
        "git add .",
        "git status looks good",
    ])
    def test_dev_chatter_detected(self, text: str) -> None:
        msg = ThreadMessage(author="Dev", timestamp="now", text=text)
        assert is_dev_chatter(msg) is True

    @pytest.mark.parametrize("text", [
        "I am reviewing Pittsburgh EIT returns",
        "The tax year shows ET-2025 instead of ET-2026",
        "PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE 1Q2026",
        "Can we confirm the PEO company name?",
        "Rippling PEO 1, Inc. is showing on all returns",
    ])
    def test_operational_messages_not_filtered(self, text: str) -> None:
        msg = ThreadMessage(author="Tony", timestamp="now", text=text)
        assert is_dev_chatter(msg) is False


class TestFilterMessages:
    def test_filters_bot_and_dev_chatter(self) -> None:
        messages = [
            ThreadMessage(author="Tony", timestamp="1", text="EIT issue found"),
            ThreadMessage(author="Claude", timestamp="2", text="I'll look into it"),
            ThreadMessage(author="Tony", timestamp="3", text="Tax year is wrong"),
            ThreadMessage(author="Cursor", timestamp="4", text="All tests pass, lint is clean"),
            ThreadMessage(author="Dev", timestamp="5", text="I implemented the fix in Phase 2"),
        ]
        filtered = filter_messages(messages)
        assert len(filtered) == 2
        assert filtered[0].text == "EIT issue found"
        assert filtered[1].text == "Tax year is wrong"

    def test_preserves_all_human_operational_messages(self) -> None:
        messages = [
            ThreadMessage(author="Tony", timestamp="1", text="Pittsburgh EIT 1Q2026"),
            ThreadMessage(
                author="Tony", timestamp="2",
                text="Tax year showing ET-2025 should be 2026",
            ),
        ]
        filtered = filter_messages(messages)
        assert len(filtered) == 2

    def test_filters_is_bot_flag(self) -> None:
        messages = [
            ThreadMessage(author="CustomApp", timestamp="1", text="Status update", is_bot=True),
            ThreadMessage(author="Tony", timestamp="2", text="Real content"),
        ]
        filtered = filter_messages(messages)
        assert len(filtered) == 1
        assert filtered[0].author == "Tony"
