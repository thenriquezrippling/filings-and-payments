"""Tests for Slack thread reading, Block Kit, and normalization (Phase 4)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft, IssueType, IssuePriority
from tax_ops_filing_bot.models.thread import ThreadMessage, NormalizedThread
from tax_ops_filing_bot.slack.blocks import (
    build_confirmation_blocks,
    build_created_message,
    build_sync_message,
    _truncate,
)
from tax_ops_filing_bot.slack.thread_reader import normalize_thread_messages


def _raw_messages() -> list[dict]:
    return [
        {"user": "U1", "text": "We need to file Q1 for CA", "ts": "1715000000.000100"},
        {"user": "U2", "text": "I'll handle it", "ts": "1715000001.000100"},
        {"user": "U3", "text": "cc @alice", "ts": "1715000002.000100"},
    ]


class TestNormalizeThreadMessages:
    def test_basic_normalization(self) -> None:
        msgs = normalize_thread_messages(_raw_messages())
        assert len(msgs) == 3
        assert all(isinstance(m, ThreadMessage) for m in msgs)

    def test_user_map(self) -> None:
        msgs = normalize_thread_messages(
            _raw_messages(), user_map={"U1": "alice", "U2": "bob"}
        )
        assert msgs[0].username == "alice"
        assert msgs[1].username == "bob"
        assert msgs[2].username == "U3"  # falls back to user_id

    def test_filters_bot_messages(self) -> None:
        msgs = normalize_thread_messages(_raw_messages(), bot_user_id="U2")
        assert len(msgs) == 2
        assert all(m.user_id != "U2" for m in msgs)

    def test_filters_join_subtype(self) -> None:
        raw = [{"user": "U1", "text": "joined", "ts": "0", "subtype": "channel_join"}]
        msgs = normalize_thread_messages(raw)
        assert len(msgs) == 0

    def test_filters_empty_text(self) -> None:
        raw = [{"user": "U1", "text": "   ", "ts": "0"}]
        msgs = normalize_thread_messages(raw)
        assert len(msgs) == 0

    def test_missing_user_field_uses_bot_id(self) -> None:
        raw = [{"bot_id": "B1", "text": "bot msg", "ts": "0"}]
        msgs = normalize_thread_messages(raw)
        assert len(msgs) == 1
        assert msgs[0].user_id == "B1"

    def test_bot_message_subtype_filtered(self) -> None:
        raw = [{"bot_id": "B1", "text": "bot msg", "ts": "0", "subtype": "bot_message"}]
        msgs = normalize_thread_messages(raw)
        assert len(msgs) == 0

    def test_preserves_order(self) -> None:
        msgs = normalize_thread_messages(_raw_messages())
        timestamps = [m.ts for m in msgs]
        assert timestamps == sorted(timestamps)


class TestBuildConfirmationBlocks:
    def _sample_draft(self) -> FilingIssueDraft:
        return FilingIssueDraft(
            summary="Q1 CA filing",
            description="File quarterly return for California.",
            issue_type=IssueType.TASK,
            priority=IssuePriority.HIGH,
            labels=["q1-filing", "state-ca"],
            parent_key="FILING-100",
            assignee_hint="alice",
        )

    def test_block_structure(self) -> None:
        blocks = build_confirmation_blocks(
            self._sample_draft(), thread_ts="123.456", channel_id="C001"
        )
        assert isinstance(blocks, list)
        assert len(blocks) == 5

    def test_header_block(self) -> None:
        blocks = build_confirmation_blocks(
            self._sample_draft(), thread_ts="123.456", channel_id="C001"
        )
        assert blocks[0]["type"] == "header"

    def test_fields_section(self) -> None:
        blocks = build_confirmation_blocks(
            self._sample_draft(), thread_ts="123.456", channel_id="C001"
        )
        fields = blocks[1]["fields"]
        field_texts = [f["text"] for f in fields]
        assert any("Q1 CA filing" in t for t in field_texts)
        assert any("High" in t for t in field_texts)
        assert any("q1-filing" in t for t in field_texts)

    def test_action_buttons(self) -> None:
        blocks = build_confirmation_blocks(
            self._sample_draft(), thread_ts="123.456", channel_id="C001"
        )
        actions = blocks[4]
        assert actions["type"] == "actions"
        elements = actions["elements"]
        assert len(elements) == 2
        assert elements[0]["action_id"] == "filing_approve"
        assert elements[1]["action_id"] == "filing_reject"

    def test_action_value_encoding(self) -> None:
        blocks = build_confirmation_blocks(
            self._sample_draft(), thread_ts="123.456", channel_id="C001"
        )
        approve = blocks[4]["elements"][0]
        assert approve["value"] == "C001|123.456"

    def test_no_labels(self) -> None:
        draft = FilingIssueDraft(summary="Test", description="Desc", labels=[])
        blocks = build_confirmation_blocks(draft, thread_ts="0", channel_id="C0")
        fields = blocks[1]["fields"]
        label_field = [f for f in fields if "Labels" in f["text"]][0]
        assert "_none_" in label_field["text"]


class TestBuildCreatedMessage:
    def test_without_base_url(self) -> None:
        blocks = build_created_message("FILING-42")
        assert "FILING-42" in blocks[0]["text"]["text"]

    def test_with_base_url(self) -> None:
        blocks = build_created_message("FILING-42", base_url="https://jira.example.com")
        text = blocks[0]["text"]["text"]
        assert "FILING-42" in text
        assert "https://jira.example.com/browse/FILING-42" in text


class TestBuildSyncMessage:
    def test_sync_message(self) -> None:
        blocks = build_sync_message("FILING-42")
        assert "FILING-42" in blocks[0]["text"]["text"]
        assert "Synced" in blocks[0]["text"]["text"]


class TestTruncate:
    def test_short_text(self) -> None:
        assert _truncate("hello", 100) == "hello"

    def test_exact_length(self) -> None:
        assert _truncate("hello", 5) == "hello"

    def test_truncation(self) -> None:
        result = _truncate("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8
