"""Fetch and normalize a Slack thread into a NormalizedThread."""

from __future__ import annotations

import logging
from typing import Any

from tax_ops_filing_bot.models.thread import NormalizedThread, ThreadMessage

logger = logging.getLogger(__name__)


def normalize_thread_messages(
    raw_messages: list[dict[str, Any]],
    *,
    user_map: dict[str, str] | None = None,
    bot_user_id: str | None = None,
) -> list[ThreadMessage]:
    """Convert raw Slack API message dicts into ``ThreadMessage`` objects.

    Parameters
    ----------
    raw_messages:
        Messages from ``conversations.replies`` (each has ``user``, ``text``, ``ts``).
    user_map:
        Optional ``{user_id: display_name}`` lookup built from ``users.info`` calls.
    bot_user_id:
        If provided, messages from this user are excluded (the bot's own messages).
    """
    user_map = user_map or {}
    result: list[ThreadMessage] = []
    for msg in raw_messages:
        uid = msg.get("user", msg.get("bot_id", "unknown"))
        if bot_user_id and uid == bot_user_id:
            continue
        if msg.get("subtype") in ("channel_join", "channel_leave", "bot_message"):
            continue
        text = msg.get("text", "")
        if not text.strip():
            continue
        result.append(
            ThreadMessage(
                user_id=uid,
                username=user_map.get(uid, uid),
                text=text,
                ts=msg.get("ts", "0"),
            )
        )
    return result


def fetch_thread(
    client: Any,
    channel: str,
    thread_ts: str,
    *,
    bot_user_id: str | None = None,
) -> NormalizedThread:
    """Use a Slack ``WebClient`` to fetch and normalize a thread.

    Parameters
    ----------
    client:
        A ``slack_sdk.WebClient`` instance (or mock with ``conversations_replies``).
    channel:
        Channel ID containing the thread.
    thread_ts:
        Timestamp of the parent message.
    bot_user_id:
        Bot user ID to filter out.
    """
    resp = client.conversations_replies(channel=channel, ts=thread_ts, limit=200)
    raw_messages: list[dict[str, Any]] = resp.get("messages", [])

    user_ids = {m.get("user", "") for m in raw_messages if m.get("user")}
    user_map: dict[str, str] = {}
    for uid in user_ids:
        if bot_user_id and uid == bot_user_id:
            continue
        try:
            info = client.users_info(user=uid)
            profile = info.get("user", {}).get("profile", {})
            user_map[uid] = profile.get("display_name") or profile.get("real_name", uid)
        except Exception:
            user_map[uid] = uid

    messages = normalize_thread_messages(
        raw_messages, user_map=user_map, bot_user_id=bot_user_id
    )
    return NormalizedThread(
        channel_id=channel,
        thread_ts=thread_ts,
        messages=messages,
    )
