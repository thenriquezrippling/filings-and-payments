"""Tests for Pydantic models (Phase 2)."""

from __future__ import annotations

import pytest

from tax_ops_filing_bot.models.thread import ThreadMessage, NormalizedThread
from tax_ops_filing_bot.models.issue_draft import (
    FilingIssueDraft,
    IssuePriority,
    IssueType,
    classify_work_type,
    generate_labels,
    resolve_parent_epic,
    strip_implementation_notes,
)


class TestThreadMessage:
    def test_basic_construction(self) -> None:
        msg = ThreadMessage(user_id="U123", username="alice", text="hello", ts="1715000000.000100")
        assert msg.user_id == "U123"
        assert msg.username == "alice"
        assert msg.text == "hello"

    def test_datetime_utc(self) -> None:
        msg = ThreadMessage(user_id="U1", text="test", ts="1715000000.000100")
        dt = msg.datetime_utc
        assert dt.year == 2024
        assert dt.tzname() == "UTC"

    def test_default_username(self) -> None:
        msg = ThreadMessage(user_id="U1", text="test", ts="0")
        assert msg.username == "unknown"


class TestNormalizedThread:
    def _make_thread(self, n_messages: int = 3) -> NormalizedThread:
        msgs = [
            ThreadMessage(
                user_id=f"U{i}",
                username=f"user{i}",
                text=f"Message {i}",
                ts=f"{1715000000 + i}.000100",
            )
            for i in range(n_messages)
        ]
        return NormalizedThread(
            channel_id="C001",
            thread_ts="1715000000.000100",
            messages=msgs,
        )

    def test_plain_text(self) -> None:
        thread = self._make_thread(2)
        text = thread.plain_text
        assert "[user0] Message 0" in text
        assert "[user1] Message 1" in text

    def test_message_count(self) -> None:
        thread = self._make_thread(5)
        assert thread.message_count == 5

    def test_empty_thread(self) -> None:
        thread = NormalizedThread(channel_id="C001", thread_ts="0")
        assert thread.plain_text == ""
        assert thread.message_count == 0


class TestFilingIssueDraft:
    def test_defaults(self) -> None:
        draft = FilingIssueDraft(summary="Test", description="Desc")
        assert draft.issue_type == IssueType.BLOCKER
        assert draft.priority == IssuePriority.MEDIUM
        assert draft.labels == []
        assert draft.parent_key is None
        assert draft.assignee_hint is None

    def test_full_construction(self) -> None:
        draft = FilingIssueDraft(
            summary="Q1 CA filing",
            description="File quarterly return for California",
            issue_type=IssueType.FILING_EXCEPTION,
            priority=IssuePriority.HIGH,
            labels=["quarterly", "state-filing"],
            parent_key="FILING-200",
            assignee_hint="alice",
        )
        assert draft.summary == "Q1 CA filing"
        assert draft.issue_type == IssueType.FILING_EXCEPTION
        assert draft.priority == IssuePriority.HIGH
        assert len(draft.labels) == 2
        assert draft.parent_key == "FILING-200"

    def test_summary_max_length(self) -> None:
        with pytest.raises(Exception):
            FilingIssueDraft(summary="x" * 256, description="d")

    def test_enum_values(self) -> None:
        assert IssuePriority.HIGHEST.value == "Highest"
        assert IssueType.BLOCKER.value == "Blocker"
        assert IssueType.FILING_EXCEPTION.value == "Filing Exception"
        assert IssueType.FEATURE_REQUEST.value == "Feature Request"
        assert IssueType.RETRO.value == "Retro"
        assert IssueType.EXECUTIVE_SUMMARY.value == "Executive Summary"

    def test_json_roundtrip(self) -> None:
        draft = FilingIssueDraft(
            summary="Test roundtrip",
            description="body",
            labels=["local-tax"],
        )
        data = draft.model_dump()
        restored = FilingIssueDraft.model_validate(data)
        assert restored == draft

    def test_description_strips_impl_notes(self) -> None:
        raw_desc = "Filing is due.\nImplementation note: use batch API\nMore context."
        draft = FilingIssueDraft(summary="Test", description=raw_desc)
        assert "Implementation note" not in draft.description
        assert "Filing is due." in draft.description
        assert "More context." in draft.description


class TestClassifyWorkType:
    def test_pittsburgh_eit_is_blocker(self) -> None:
        text = "Pittsburgh EIT filing is blocked, need resolution ASAP"
        assert classify_work_type(text) == IssueType.BLOCKER

    def test_eit_keyword_is_blocker(self) -> None:
        assert classify_work_type("EIT underpayment issue") == IssueType.BLOCKER

    def test_deadline_is_blocker(self) -> None:
        assert classify_work_type("approaching deadline for submission") == IssueType.BLOCKER

    def test_penalty_is_blocker(self) -> None:
        assert classify_work_type("penalty notice received from state") == IssueType.BLOCKER

    def test_cannot_file_is_blocker(self) -> None:
        assert classify_work_type("we cannot file the quarterly return") == IssueType.BLOCKER

    def test_filing_error_is_exception(self) -> None:
        assert classify_work_type("filing submission error on form 941") == IssueType.FILING_EXCEPTION

    def test_rejection_is_exception(self) -> None:
        assert classify_work_type("return was rejected by the state portal") == IssueType.FILING_EXCEPTION

    def test_mismatch_is_exception(self) -> None:
        assert classify_work_type("SSN mismatch on W-2 forms") == IssueType.FILING_EXCEPTION

    def test_feature_request(self) -> None:
        assert classify_work_type("feature request: add bulk upload") == IssueType.FEATURE_REQUEST

    def test_enhancement_is_feature(self) -> None:
        assert classify_work_type("enhancement to the reporting dashboard") == IssueType.FEATURE_REQUEST

    def test_retro(self) -> None:
        assert classify_work_type("Q1 retrospective discussion") == IssueType.RETRO

    def test_postmortem_is_retro(self) -> None:
        assert classify_work_type("post-mortem for missed filing") == IssueType.RETRO

    def test_executive_summary(self) -> None:
        assert classify_work_type("executive summary for board meeting") == IssueType.EXECUTIVE_SUMMARY

    def test_status_report_is_exec_summary(self) -> None:
        assert classify_work_type("weekly status report for tax ops") == IssueType.EXECUTIVE_SUMMARY

    def test_fallback_is_blocker(self) -> None:
        assert classify_work_type("some random unclassifiable text xyz") == IssueType.BLOCKER


class TestResolveParentEpic:
    def test_eit_maps_to_101(self) -> None:
        assert resolve_parent_epic("Pittsburgh EIT filing blocked") == "FILING-101"

    def test_earned_income_tax_maps_to_101(self) -> None:
        assert resolve_parent_epic("earned income tax issue") == "FILING-101"

    def test_state_filing_maps_to_200(self) -> None:
        assert resolve_parent_epic("state filing for California") == "FILING-200"

    def test_quarterly_filing_maps_to_200(self) -> None:
        assert resolve_parent_epic("Q1 filing deadline approaching") == "FILING-200"

    def test_federal_maps_to_300(self) -> None:
        assert resolve_parent_epic("federal filing for 2025") == "FILING-300"

    def test_amendment_maps_to_400(self) -> None:
        assert resolve_parent_epic("need to file an amendment") == "FILING-400"

    def test_penalty_maps_to_500(self) -> None:
        assert resolve_parent_epic("penalty notice from IRS") == "FILING-500"

    def test_no_match_returns_none(self) -> None:
        assert resolve_parent_epic("general discussion about process") is None

    def test_case_insensitive(self) -> None:
        assert resolve_parent_epic("PITTSBURGH EIT BLOCKED") == "FILING-101"


class TestGenerateLabels:
    def test_pittsburgh_eit(self) -> None:
        labels = generate_labels("Pittsburgh EIT filing issue")
        assert "pittsburgh" in labels
        assert "local-tax" in labels

    def test_quarterly(self) -> None:
        labels = generate_labels("Q1 state filing deadline")
        assert "quarterly" in labels
        assert "state-filing" in labels

    def test_federal(self) -> None:
        labels = generate_labels("federal annual return")
        assert "federal" in labels

    def test_amendment(self) -> None:
        labels = generate_labels("we need an amendment filed")
        assert "amendment" in labels

    def test_urgent_deadline(self) -> None:
        labels = generate_labels("urgent: deadline approaching")
        assert "urgent" in labels
        assert "deadline" in labels

    def test_no_match_returns_empty(self) -> None:
        labels = generate_labels("general discussion topic")
        assert labels == []

    def test_sorted_and_deduplicated(self) -> None:
        labels = generate_labels("EIT earned income tax Pittsburgh")
        assert labels == sorted(set(labels))


class TestStripImplementationNotes:
    def test_removes_impl_note_line(self) -> None:
        text = "Real content.\nImplementation note: use batch API\nMore content."
        result = strip_implementation_notes(text)
        assert "Implementation note" not in result
        assert "Real content." in result
        assert "More content." in result

    def test_removes_html_comments(self) -> None:
        text = "Visible text.\n<!-- internal: use v2 endpoint -->\nMore text."
        result = strip_implementation_notes(text)
        assert "internal" not in result
        assert "Visible text." in result

    def test_removes_todo_comments(self) -> None:
        text = "Description.\nTODO: refactor this later\nDetails."
        result = strip_implementation_notes(text)
        assert "TODO" not in result
        assert "Description." in result

    def test_removes_internal_markers(self) -> None:
        text = "Public info.\n[internal] This is for devs only\nEnd."
        result = strip_implementation_notes(text)
        assert "[internal]" not in result
        assert "Public info." in result

    def test_preserves_clean_text(self) -> None:
        text = "This is a clean description with no notes."
        assert strip_implementation_notes(text) == text

    def test_collapses_excess_newlines(self) -> None:
        text = "First.\n\n\n\n\nSecond."
        result = strip_implementation_notes(text)
        assert "\n\n\n" not in result
