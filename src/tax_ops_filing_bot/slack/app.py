"""Slack Bolt application: app_mention handler, confirmation actions, sync command."""

from __future__ import annotations

import logging
import os
from typing import Any

from slack_bolt import App
from slack_sdk import WebClient

from tax_ops_filing_bot.jira.client import JiraClient, JiraConfig
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.models.schemas import SyncRequest
from tax_ops_filing_bot.services.intake import IntakeService
from tax_ops_filing_bot.services.sync import SyncService
from tax_ops_filing_bot.slack.blocks import (
    draft_confirmation_blocks,
    error_blocks,
    issue_created_blocks,
    sync_success_blocks,
)
from tax_ops_filing_bot.slack.thread_fetch import fetch_thread, parse_sync_command

logger = logging.getLogger(__name__)

_pending_drafts: dict[str, Any] = {}


def create_app() -> App:
    """Build and return a configured Bolt App with all listeners registered."""
    app = App(
        token=os.environ["SLACK_BOT_TOKEN"],
        name="tax-ops-filing-bot",
    )

    jira_config = JiraConfig(
        base_url=os.environ["JIRA_BASE_URL"],
        email=os.environ["JIRA_EMAIL"],
        api_token=os.environ["JIRA_API_TOKEN"],
        project_key=os.environ.get("JIRA_PROJECT_KEY", "FILING"),
    )
    jira = JiraClient(jira_config)
    llm = AnthropicClient(api_key=os.environ["ANTHROPIC_API_KEY"])
    intake_svc = IntakeService(llm=llm, jira=jira)
    sync_svc = SyncService(jira=jira)

    _register_listeners(app, intake_svc, sync_svc, jira_config)
    return app


def _register_listeners(
    app: App,
    intake_svc: IntakeService,
    sync_svc: SyncService,
    jira_config: JiraConfig,
) -> None:
    @app.event("app_mention")
    def handle_mention(event: dict[str, Any], client: WebClient, say: Any) -> None:
        text: str = event.get("text", "")
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event.get("ts", "")

        if not thread_ts or thread_ts == event.get("ts"):
            say(
                text="Please mention me inside a thread so I can read the conversation.",
                thread_ts=event.get("ts"),
            )
            return

        sync_key = parse_sync_command(text)
        if sync_key:
            _handle_sync(sync_svc, client, say, channel, thread_ts, sync_key, jira_config)
            return

        _handle_intake(intake_svc, client, say, channel, thread_ts)

    @app.action("filing_create_confirm")
    def handle_confirm(ack: Any, body: dict[str, Any], client: WebClient) -> None:
        ack()
        thread_ts = body["actions"][0]["value"]
        channel = body["channel"]["id"]

        draft_data = _pending_drafts.pop(thread_ts, None)
        if draft_data is None:
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Draft expired or already processed.",
            )
            return

        draft = draft_data["draft"]
        thread = draft_data["thread"]
        jira_url = draft_data["jira_url"]

        try:
            issue = intake_svc.create_issue(draft, thread)
            blocks = issue_created_blocks(issue.key, draft.summary)
            for b in blocks:
                if "text" in b and "mrkdwn" in str(b.get("text", {}).get("type", "")):
                    b["text"]["text"] = b["text"]["text"].replace("{jira_url}", jira_url)

            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"Created {issue.key}",
                blocks=blocks,
            )
        except Exception as exc:
            logger.exception("Failed to create Jira issue")
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Failed to create ticket.",
                blocks=error_blocks(str(exc)),
            )

    @app.action("filing_create_cancel")
    def handle_cancel(ack: Any, body: dict[str, Any], client: WebClient) -> None:
        ack()
        thread_ts = body["actions"][0]["value"]
        _pending_drafts.pop(thread_ts, None)
        channel = body["channel"]["id"]
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="Ticket creation cancelled.",
        )


def _handle_intake(
    intake_svc: IntakeService,
    client: WebClient,
    say: Any,
    channel: str,
    thread_ts: str,
) -> None:
    try:
        thread = fetch_thread(client, channel, thread_ts)
        draft = intake_svc.extract_draft(thread)
        _pending_drafts[thread_ts] = {
            "draft": draft,
            "thread": thread,
            "jira_url": os.environ.get("JIRA_BASE_URL", ""),
        }
        blocks = draft_confirmation_blocks(draft, thread_ts)
        say(
            text=f"Draft: {draft.summary}",
            blocks=blocks,
            thread_ts=thread_ts,
        )
    except Exception as exc:
        logger.exception("Intake extraction failed")
        say(
            text="Failed to extract issue from thread.",
            blocks=error_blocks(str(exc)),
            thread_ts=thread_ts,
        )


def _handle_sync(
    sync_svc: SyncService,
    client: WebClient,
    say: Any,
    channel: str,
    thread_ts: str,
    issue_key: str,
    jira_config: JiraConfig,
) -> None:
    try:
        thread = fetch_thread(client, channel, thread_ts)
        request = SyncRequest(
            issue_key=issue_key,
            thread=thread,
        )
        sync_svc.sync(request)
        blocks = sync_success_blocks(issue_key, len(thread.messages))
        for b in blocks:
            if "text" in b and "mrkdwn" in str(b.get("text", {}).get("type", "")):
                b["text"]["text"] = b["text"]["text"].replace(
                    "{jira_url}", jira_config.base_url
                )
        say(
            text=f"Synced to {issue_key}",
            blocks=blocks,
            thread_ts=thread_ts,
        )
    except Exception as exc:
        logger.exception("Sync failed for %s", issue_key)
        say(
            text=f"Failed to sync to {issue_key}.",
            blocks=error_blocks(str(exc)),
            thread_ts=thread_ts,
        )
