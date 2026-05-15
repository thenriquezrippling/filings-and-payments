"""Slack Bolt application with app_mention and action handlers."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from slack_bolt import App

from tax_ops_filing_bot.jira.client import JiraClient
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.issue_draft import FilingIssueDraft
from tax_ops_filing_bot.services.commands import parse_sync_command
from tax_ops_filing_bot.services.intake import IntakeService
from tax_ops_filing_bot.services.sync import SyncService
from tax_ops_filing_bot.slack.blocks import (
    build_confirmation_blocks,
    build_created_message,
    build_sync_message,
)
from tax_ops_filing_bot.slack.thread_reader import fetch_thread

logger = logging.getLogger(__name__)

_pending_drafts: dict[str, FilingIssueDraft] = {}


def create_app(
    *,
    llm: AnthropicClient | None = None,
    jira: JiraClient | None = None,
    bot_user_id: str | None = None,
    slack_bot_token: str | None = None,
) -> App:
    """Build and return a configured Bolt ``App`` with all listeners registered.

    All collaborators (llm, jira) are injectable for testing. When omitted,
    they fall back to env-var-based defaults or mock mode.
    """
    token = slack_bot_token or os.environ.get("SLACK_BOT_TOKEN", "")
    app = App(token=token, token_verification_enabled=False)

    if llm is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "mock")
        llm = AnthropicClient(api_key=api_key)
    if jira is None:
        jira = JiraClient(
            base_url=os.environ.get("JIRA_BASE_URL", "mock"),
            email=os.environ.get("JIRA_EMAIL", ""),
            api_token=os.environ.get("JIRA_API_TOKEN", ""),
            project_key=os.environ.get("JIRA_PROJECT_KEY", "FILING"),
        )
    if bot_user_id is None:
        bot_user_id = os.environ.get("SLACK_BOT_USER_ID", "")

    intake = IntakeService(llm)
    sync_svc = SyncService(jira)
    _jira = jira

    @app.event("app_mention")
    def handle_mention(event: dict[str, Any], client: Any, say: Any) -> None:
        text: str = event.get("text", "")
        channel: str = event.get("channel", "")
        thread_ts: str = event.get("thread_ts") or event.get("ts", "")

        sync_cmd = parse_sync_command(text)
        if sync_cmd:
            _handle_sync(client, say, channel, thread_ts, sync_cmd.issue_key, sync_svc, bot_user_id or "")
            return

        _handle_intake(client, say, channel, thread_ts, intake, bot_user_id or "")

    @app.action("filing_approve")
    def handle_approve(ack: Any, body: dict[str, Any], client: Any) -> None:
        ack()
        action = body["actions"][0]
        value = action["value"]
        channel_id, thread_ts = value.split("|", 1)

        draft_key = f"{channel_id}:{thread_ts}"
        draft = _pending_drafts.pop(draft_key, None)
        if draft is None:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="⚠️ Draft expired or already processed.",
            )
            return

        created = _jira.create_issue(draft)
        blocks = build_created_message(
            created.key,
            base_url=_jira.base_url if not _jira.is_mock else "",
        )
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"Created {created.key}",
            blocks=blocks,
        )

    @app.action("filing_reject")
    def handle_reject(ack: Any, body: dict[str, Any], client: Any) -> None:
        ack()
        action = body["actions"][0]
        value = action["value"]
        channel_id, thread_ts = value.split("|", 1)

        draft_key = f"{channel_id}:{thread_ts}"
        _pending_drafts.pop(draft_key, None)

        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="❌ Ticket creation cancelled.",
        )

    return app


def _handle_intake(
    client: Any,
    say: Any,
    channel: str,
    thread_ts: str,
    intake: IntakeService,
    bot_user_id: str,
) -> None:
    thread = fetch_thread(client, channel, thread_ts, bot_user_id=bot_user_id or None)
    if not thread.messages:
        say(text="No messages found in this thread.", thread_ts=thread_ts)
        return

    result = intake.infer_draft(thread)
    draft_key = f"{channel}:{thread_ts}"
    _pending_drafts[draft_key] = result.draft

    blocks = build_confirmation_blocks(
        result.draft, thread_ts=thread_ts, channel_id=channel
    )
    say(text=f"Draft: {result.draft.summary}", blocks=blocks, thread_ts=thread_ts)


def _handle_sync(
    client: Any,
    say: Any,
    channel: str,
    thread_ts: str,
    issue_key: str,
    sync_svc: SyncService,
    bot_user_id: str,
) -> None:
    thread = fetch_thread(client, channel, thread_ts, bot_user_id=bot_user_id or None)
    result = sync_svc.sync_thread(thread, issue_key)
    if result.success:
        blocks = build_sync_message(issue_key)
        say(text=f"Synced to {issue_key}", blocks=blocks, thread_ts=thread_ts)
    else:
        say(text=f"⚠️ Could not sync to {issue_key} — issue not found.", thread_ts=thread_ts)
