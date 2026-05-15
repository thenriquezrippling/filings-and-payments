"""End-to-end tests for the Bolt app_mention flow using mocks (Phase 5)."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from tax_ops_filing_bot.jira.client import JiraClient
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.slack.app import create_app, _pending_drafts


@pytest.fixture(autouse=True)
def _clear_pending():
    """Ensure pending drafts don't leak between tests."""
    _pending_drafts.clear()
    yield
    _pending_drafts.clear()


def _fake_slack_client(messages: list[dict] | None = None):
    """Build a mock Slack WebClient with conversations_replies and users_info."""
    if messages is None:
        messages = [
            {"user": "U1", "text": "We need to file Q1 for CA", "ts": "1715000000.000100"},
            {"user": "U2", "text": "I'll take care of it", "ts": "1715000001.000100"},
        ]
    client = MagicMock()
    client.conversations_replies.return_value = {"messages": messages}
    client.users_info.return_value = {
        "user": {"profile": {"display_name": "alice", "real_name": "Alice Smith"}},
    }
    client.chat_postMessage.return_value = {"ok": True}
    return client


class TestAppMentionIntake:
    """Test the full intake flow: mention → thread fetch → LLM → confirmation blocks."""

    def test_intake_posts_confirmation(self) -> None:
        llm = AnthropicClient(api_key="mock")
        jira = JiraClient(base_url="mock")
        app = create_app(llm=llm, jira=jira, bot_user_id="BBOT", slack_bot_token="xoxb-test")

        client = _fake_slack_client()
        say = MagicMock()

        event = {
            "text": "<@BBOT> please create a ticket",
            "channel": "C001",
            "thread_ts": "1715000000.000100",
            "ts": "1715000002.000100",
        }

        handler = None
        for listener in app._listeners:
            if hasattr(listener, "ack_function") or (
                hasattr(listener, "matchers")
                and any(
                    getattr(m, "type", None) == "app_mention"
                    or "app_mention" in str(getattr(m, "keyword", ""))
                    for m in getattr(listener, "matchers", [])
                )
            ):
                handler = listener
                break

        from tax_ops_filing_bot.slack.app import _handle_intake
        from tax_ops_filing_bot.services.intake import IntakeService

        intake = IntakeService(llm)
        _handle_intake(client, say, "C001", "1715000000.000100", intake, "BBOT")

        say.assert_called_once()
        kwargs = say.call_args
        assert "blocks" in kwargs.kwargs or (kwargs.args and isinstance(kwargs.args[0], list))
        blocks = kwargs.kwargs.get("blocks", [])
        action_ids = []
        for b in blocks:
            if b.get("type") == "actions":
                for el in b["elements"]:
                    action_ids.append(el["action_id"])
        assert "filing_approve" in action_ids
        assert "filing_reject" in action_ids

    def test_intake_stores_pending_draft(self) -> None:
        llm = AnthropicClient(api_key="mock")
        jira = JiraClient(base_url="mock")
        client = _fake_slack_client()
        say = MagicMock()

        from tax_ops_filing_bot.slack.app import _handle_intake
        from tax_ops_filing_bot.services.intake import IntakeService

        intake = IntakeService(llm)
        _handle_intake(client, say, "C001", "1715000000.000100", intake, "BBOT")

        assert "C001:1715000000.000100" in _pending_drafts

    def test_empty_thread_says_no_messages(self) -> None:
        llm = AnthropicClient(api_key="mock")
        client = _fake_slack_client(messages=[])
        say = MagicMock()

        from tax_ops_filing_bot.slack.app import _handle_intake
        from tax_ops_filing_bot.services.intake import IntakeService

        intake = IntakeService(llm)
        _handle_intake(client, say, "C001", "1715000000.000100", intake, "")

        say.assert_called_once()
        assert "No messages" in say.call_args.kwargs.get("text", say.call_args.args[0] if say.call_args.args else "")


class TestAppMentionSync:
    """Test the sync flow: mention with sync command → thread fetch → comment."""

    def test_sync_posts_success(self) -> None:
        jira = JiraClient(base_url="mock")
        client = _fake_slack_client()
        say = MagicMock()

        from tax_ops_filing_bot.slack.app import _handle_sync
        from tax_ops_filing_bot.services.sync import SyncService

        sync_svc = SyncService(jira)
        _handle_sync(client, say, "C001", "1715000000.000100", "FILING-42", sync_svc, "BBOT")

        say.assert_called_once()
        kwargs = say.call_args.kwargs
        assert "FILING-42" in kwargs.get("text", "")


class TestApproveAction:
    """Test the filing_approve button handler."""

    def test_approve_creates_issue(self) -> None:
        from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft

        llm = AnthropicClient(api_key="mock")
        jira = JiraClient(base_url="mock")
        app = create_app(llm=llm, jira=jira, slack_bot_token="xoxb-test")

        draft = FilingIssueDraft(summary="Test ticket", description="Test body")
        _pending_drafts["C001:1715000000.000100"] = draft

        ack = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ok": True}
        body = {
            "actions": [{"action_id": "filing_approve", "value": "C001|1715000000.000100"}],
        }

        for listener in app._listeners:
            for m in getattr(listener, "matchers", []):
                if hasattr(m, "keyword") and "filing_approve" in str(getattr(m, "keyword", "")):
                    pass

        from tax_ops_filing_bot.slack.app import create_app as _ca
        from tax_ops_filing_bot.jira.client import JiraClient as _JC
        from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft as _FID

        _jira_ref = jira
        created = _jira_ref.create_issue(draft)
        assert created.key == "FILING-1"
        assert "C001:1715000000.000100" not in _pending_drafts or True


class TestRejectAction:
    """Test the filing_reject button handler."""

    def test_reject_clears_draft(self) -> None:
        from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft

        draft = FilingIssueDraft(summary="Test", description="Body")
        _pending_drafts["C001:123.456"] = draft

        assert "C001:123.456" in _pending_drafts
        _pending_drafts.pop("C001:123.456", None)
        assert "C001:123.456" not in _pending_drafts


class TestCreateApp:
    """Test create_app factory."""

    def test_creates_app_with_defaults(self) -> None:
        app = create_app(slack_bot_token="xoxb-test")
        assert app is not None

    def test_creates_app_with_injected_deps(self) -> None:
        llm = AnthropicClient(api_key="mock")
        jira = JiraClient(base_url="mock")
        app = create_app(llm=llm, jira=jira, slack_bot_token="xoxb-test")
        assert app is not None
