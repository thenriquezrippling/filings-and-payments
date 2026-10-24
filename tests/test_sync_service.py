"""Tests for persistent two-way Jira <-> Slack thread synchronization.

Covers:
  - Jira issue URL posted in Slack thread (native card unfurl)
  - Initial linking (URL marker + minimal Jira comment)
  - Sync-only command
  - Slack reply -> Jira comment
  - Jira comment -> Slack reply
  - Duplicate prevention
  - Infinite loop prevention
  - No duplicate sync markers
  - No duplicate Jira link comments
  - New ticket creation automatically enables sync
  - SyncLink metadata storage
  - Native Sync Thread cannot be triggered programmatically (fallback to custom)
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

from tax_ops_filing_bot.services.sync_service import (
    DEFAULT_JIRA_BASE_URL,
    LINK_COMMENT_MARKER,
    SYNCED_FROM_SLACK_MARKER,
    ContinuousSyncResult,
    InMemorySyncLinkStore,
    SyncLink,
    SyncResult,
    SyncService,
    build_initial_link_comment,
    build_jira_comment_adf,
    build_jira_issue_url,
    build_jira_to_slack_message,
    build_slack_to_jira_comment,
    build_sync_marker,
    jira_has_link_comment,
    jira_has_thread_comment,
    parse_sync_command,
    thread_has_sync_marker,
    _message_is_sync_marker,
)

JIRA_BASE = "https://acme.atlassian.net"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mock_slack(
    existing_messages: list[dict] | None = None,
    *,
    bot_user_id: str | None = None,
):
    slack = MagicMock()
    slack.conversations_replies.return_value = {
        "messages": existing_messages or [],
    }
    slack.chat_postMessage.return_value = {"ok": True}
    return slack


def _mock_jira(existing_comments: list[dict] | None = None):
    jira = MagicMock()
    jira.get_comments.return_value = existing_comments or []
    jira.add_comment.return_value = {"id": "90001"}
    return jira


def _adf_comment(text: str, *, comment_id: str = "1", author: str = "Unknown") -> dict:
    """Build a mock Jira comment dict with ADF body."""
    return {
        "id": comment_id,
        "author": {"displayName": author, "accountId": "acct-123"},
        "body": {
            "content": [
                {"content": [{"type": "text", "text": text}]}
            ]
        },
    }


# ===========================================================================
# 1. Jira issue URL builder
# ===========================================================================

class TestBuildJiraIssueUrl:
    def test_basic_url(self) -> None:
        url = build_jira_issue_url("https://acme.atlassian.net", "FILING-1234")
        assert url == "https://acme.atlassian.net/browse/FILING-1234"

    def test_trailing_slash_stripped(self) -> None:
        url = build_jira_issue_url("https://acme.atlassian.net/", "FILING-42")
        assert url == "https://acme.atlassian.net/browse/FILING-42"

    def test_default_base_url(self) -> None:
        url = build_jira_issue_url(DEFAULT_JIRA_BASE_URL, "FILING-6152")
        assert url == f"{DEFAULT_JIRA_BASE_URL}/browse/FILING-6152"


# ===========================================================================
# 2. Build sync marker (now includes Jira URL)
# ===========================================================================

class TestBuildSyncMarker:
    def test_contains_jira_url(self) -> None:
        marker = build_sync_marker("FILING-1234", JIRA_BASE)
        assert "https://acme.atlassian.net/browse/FILING-1234" in marker

    def test_contains_sync_key_reference(self) -> None:
        marker = build_sync_marker("FILING-1234", JIRA_BASE)
        assert "Sync [FILING-1234]" in marker

    def test_url_on_first_line(self) -> None:
        marker = build_sync_marker("FILING-6152", JIRA_BASE)
        lines = marker.split("\n")
        assert lines[0] == "https://acme.atlassian.net/browse/FILING-6152"

    def test_default_base_url_used(self) -> None:
        marker = build_sync_marker("FILING-99")
        assert DEFAULT_JIRA_BASE_URL in marker
        assert "/browse/FILING-99" in marker

    def test_format_large_number(self) -> None:
        marker = build_sync_marker("FILING-6152", JIRA_BASE)
        assert "Sync [FILING-6152]" in marker


# ===========================================================================
# 3. Parse sync command
# ===========================================================================

class TestParseSyncCommand:
    def test_basic(self) -> None:
        assert parse_sync_command("sync this thread to FILING-1234") == "FILING-1234"

    def test_with_mention(self) -> None:
        assert parse_sync_command("<@U123> sync this thread to FILING-42") == "FILING-42"

    def test_case_insensitive(self) -> None:
        assert parse_sync_command("Sync This Thread To filing-99") == "FILING-99"

    def test_no_match(self) -> None:
        assert parse_sync_command("please create a ticket") is None


# ===========================================================================
# 4. Thread has sync marker (URL + legacy)
# ===========================================================================

class TestThreadHasSyncMarker:
    def test_found_by_url(self) -> None:
        msgs = [{"text": "https://acme.atlassian.net/browse/FILING-1234\nSync [FILING-1234]"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is True

    def test_found_by_legacy_marker(self) -> None:
        msgs = [{"text": "Sync [FILING-1234]"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is True

    def test_found_by_url_only(self) -> None:
        msgs = [{"text": "https://acme.atlassian.net/browse/FILING-1234"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is True

    def test_not_found(self) -> None:
        msgs = [{"text": "Hello world"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is False

    def test_different_key_not_matched(self) -> None:
        msgs = [{"text": "https://acme.atlassian.net/browse/FILING-5555"}]
        assert thread_has_sync_marker(msgs, "FILING-1234") is False

    def test_empty_messages(self) -> None:
        assert thread_has_sync_marker([], "FILING-1234") is False


# ===========================================================================
# 5. _message_is_sync_marker
# ===========================================================================

class TestMessageIsSyncMarker:
    def test_jira_url_detected(self) -> None:
        assert _message_is_sync_marker("https://acme.atlassian.net/browse/FILING-1234") is True

    def test_legacy_sync_marker_detected(self) -> None:
        assert _message_is_sync_marker("Sync [FILING-1234]") is True

    def test_full_sync_message_detected(self) -> None:
        msg = "https://acme.atlassian.net/browse/FILING-1234\nSync [FILING-1234]"
        assert _message_is_sync_marker(msg) is True

    def test_regular_message_not_detected(self) -> None:
        assert _message_is_sync_marker("The agency confirmed the filing.") is False

    def test_partial_url_not_detected(self) -> None:
        assert _message_is_sync_marker("check out acme.atlassian.net") is False


# ===========================================================================
# 6. Jira has link comment (new) + thread comment (backward compat)
# ===========================================================================

class TestJiraHasLinkComment:
    def test_found_with_permalink(self) -> None:
        comment_text = build_initial_link_comment("https://slack.com/archives/C001/p123456")
        comments = [_adf_comment(comment_text)]
        assert jira_has_link_comment(comments) is True

    def test_found_without_permalink(self) -> None:
        comment_text = build_initial_link_comment(None)
        comments = [_adf_comment(comment_text)]
        assert jira_has_link_comment(comments) is True

    def test_not_found(self) -> None:
        comments = [_adf_comment("Some other comment")]
        assert jira_has_link_comment(comments) is False

    def test_empty_comments(self) -> None:
        assert jira_has_link_comment([]) is False


class TestJiraHasThreadComment:
    def test_found_in_adf_comment(self) -> None:
        comments = [_adf_comment("Thread timestamp: 123.456")]
        assert jira_has_thread_comment(comments, "123.456") is True

    def test_not_found(self) -> None:
        comments = [_adf_comment("Some other comment")]
        assert jira_has_thread_comment(comments, "123.456") is False


# ===========================================================================
# 7. Message format helpers
# ===========================================================================

class TestBuildInitialLinkComment:
    def test_includes_permalink(self) -> None:
        result = build_initial_link_comment("https://slack.com/archives/C001/p123456")
        assert "https://slack.com/archives/C001/p123456" in result

    def test_includes_marker_text(self) -> None:
        result = build_initial_link_comment("https://slack.com/archives/C001/p123456")
        assert LINK_COMMENT_MARKER in result

    def test_starts_with_linked_slack_thread(self) -> None:
        result = build_initial_link_comment("https://slack.com/archives/C001/p123456")
        assert result.startswith("Linked Slack thread:")

    def test_format_with_permalink(self) -> None:
        result = build_initial_link_comment("https://slack.com/archives/C001/p123456")
        expected = (
            "Linked Slack thread: https://slack.com/archives/C001/p123456\n"
            "Linked Slack thread for ongoing discussion and updates."
        )
        assert result == expected

    def test_format_without_permalink(self) -> None:
        result = build_initial_link_comment(None)
        expected = (
            "Linked Slack thread:\n"
            "Linked Slack thread for ongoing discussion and updates."
        )
        assert result == expected

    def test_no_channel_id_in_output(self) -> None:
        result = build_initial_link_comment("https://slack.com/archives/C001/p123456")
        lines = result.split("\n")
        assert all("C001" not in line for line in lines if "slack.com" not in line)

    def test_no_verbose_metadata(self) -> None:
        result = build_initial_link_comment("https://slack.com/archives/C001/p123456")
        assert "timestamp" not in result.lower()
        assert "transcript" not in result.lower()
        assert "summary" not in result.lower()
        assert "trigger" not in result.lower()


class TestBuildSlackToJiraComment:
    def test_format(self) -> None:
        result = build_slack_to_jira_comment(
            "Tony Henriquez", "The agency confirmed the filing was accepted.",
        )
        assert result == (
            "Tony Henriquez (Slack): The agency confirmed the filing was accepted."
            f"\n{SYNCED_FROM_SLACK_MARKER}"
        )

    def test_contains_marker(self) -> None:
        result = build_slack_to_jira_comment("Alice", "Hello")
        assert SYNCED_FROM_SLACK_MARKER in result


class TestBuildJiraToSlackMessage:
    def test_format(self) -> None:
        result = build_jira_to_slack_message(
            "Kapil Mohan",
            "Engineering identified the root cause and deployed a fix.",
        )
        assert result == (
            "Kapil Mohan (Jira): Engineering identified the root cause and deployed a fix."
        )


class TestBuildJiraCommentAdf:
    def test_structure(self) -> None:
        adf = build_jira_comment_adf("Test text")
        assert adf["body"]["type"] == "doc"
        assert adf["body"]["version"] == 1
        content = adf["body"]["content"][0]["content"][0]
        assert content["type"] == "text"
        assert content["text"] == "Test text"


# ===========================================================================
# 8. SyncLink and InMemorySyncLinkStore
# ===========================================================================

class TestSyncLink:
    def test_defaults(self) -> None:
        link = SyncLink(issue_key="FILING-1", channel_id="C001", thread_ts="100.0")
        assert link.permalink is None
        assert link.jira_base_url is None
        assert link.last_synced_slack_ts is None
        assert link.last_synced_jira_comment_id is None

    def test_with_jira_base_url(self) -> None:
        link = SyncLink(
            issue_key="FILING-1", channel_id="C001", thread_ts="100.0",
            jira_base_url=JIRA_BASE,
        )
        assert link.jira_base_url == JIRA_BASE


class TestInMemorySyncLinkStore:
    def test_save_and_retrieve_by_issue(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(issue_key="FILING-1", channel_id="C001", thread_ts="100.0")
        store.save(link)
        assert store.get_by_issue("FILING-1") is link

    def test_save_and_retrieve_by_thread(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(issue_key="FILING-1", channel_id="C001", thread_ts="100.0")
        store.save(link)
        assert store.get_by_thread("C001", "100.0") is link

    def test_get_nonexistent_returns_none(self) -> None:
        store = InMemorySyncLinkStore()
        assert store.get_by_issue("FILING-999") is None
        assert store.get_by_thread("C999", "0.0") is None

    def test_update_preserves_identity(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(issue_key="FILING-1", channel_id="C001", thread_ts="100.0")
        store.save(link)
        link.last_synced_slack_ts = "200.0"
        store.save(link)
        assert store.get_by_issue("FILING-1").last_synced_slack_ts == "200.0"

    def test_links_property(self) -> None:
        store = InMemorySyncLinkStore()
        store.save(SyncLink(issue_key="FILING-1", channel_id="C001", thread_ts="100.0"))
        store.save(SyncLink(issue_key="FILING-2", channel_id="C002", thread_ts="200.0"))
        assert len(store.links) == 2


# ===========================================================================
# 9. Initial link — sync after creation
# ===========================================================================

class TestSyncServiceAfterCreation:
    def test_posts_jira_issue_url(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.sync_marker_posted is True
        slack.chat_postMessage.assert_called_once()
        call_kwargs = slack.chat_postMessage.call_args
        text = call_kwargs.kwargs.get("text", "")
        assert "https://acme.atlassian.net/browse/FILING-1234" in text
        assert "Sync [FILING-1234]" in text

    def test_returns_jira_url(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        assert result.jira_url == "https://acme.atlassian.net/browse/FILING-1234"

    def test_adds_jira_comment_with_permalink(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
            transcript="EIT issue found",
        )
        assert result.jira_comment_added is True
        jira.add_comment.assert_called_once()
        comment_text = jira.add_comment.call_args[0][1]
        assert "https://slack.com/archives/C001/p123456" in comment_text
        assert LINK_COMMENT_MARKER in comment_text
        assert comment_text == build_initial_link_comment(
            "https://slack.com/archives/C001/p123456"
        )

    def test_jira_comment_without_permalink(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        assert result.jira_comment_added is True
        comment_text = jira.add_comment.call_args[0][1]
        assert LINK_COMMENT_MARKER in comment_text
        assert comment_text == build_initial_link_comment(None)

    def test_minimal_jira_comment_has_no_standalone_channel_id(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
        )
        comment_text = jira.add_comment.call_args[0][1]
        stripped = comment_text.replace(
            "https://slack.com/archives/C001/p123456", ""
        )
        assert "C001" not in stripped

    def test_minimal_jira_comment_has_no_thread_ts(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
        )
        comment_text = jira.add_comment.call_args[0][1]
        assert "123.456" not in comment_text

    def test_minimal_jira_comment_has_no_transcript(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
            transcript="EIT issue found in Pittsburgh",
        )
        comment_text = jira.add_comment.call_args[0][1]
        assert "EIT issue found" not in comment_text
        assert "Pittsburgh" not in comment_text

    def test_minimal_jira_comment_has_no_verbose_metadata(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
            transcript="Some transcript content",
        )
        comment_text = jira.add_comment.call_args[0][1]
        assert "channel" not in comment_text.lower() or "Linked Slack" in comment_text
        assert "timestamp" not in comment_text.lower()
        assert "transcript" not in comment_text.lower()
        assert "summary" not in comment_text.lower()
        assert "table" not in comment_text.lower()

    def test_creates_sync_link(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
        )
        link = store.get_by_issue("FILING-1234")
        assert link is not None
        assert link.channel_id == "C001"
        assert link.thread_ts == "123.456"
        assert link.permalink == "https://slack.com/archives/C001/p123456"
        assert link.jira_base_url == JIRA_BASE

    def test_new_ticket_creation_auto_enables_sync(self) -> None:
        """After ticket creation, the sync link exists and can be used for two-way sync."""
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-6152",
            channel="C001",
            thread_ts="100.0",
        )
        link = store.get_by_issue("FILING-6152")
        assert link is not None
        assert link.issue_key == "FILING-6152"
        assert link.last_synced_slack_ts is not None

    def test_slack_message_contains_browsable_url(self) -> None:
        """The Slack message must include the full Jira browse URL for native unfurl."""
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-6152",
            channel="C001",
            thread_ts="100.0",
        )
        posted_text = slack.chat_postMessage.call_args.kwargs["text"]
        assert posted_text.startswith("https://")
        assert "/browse/FILING-6152" in posted_text


# ===========================================================================
# 10. Sync-only command
# ===========================================================================

class TestSyncServiceSyncOnly:
    def test_sync_only_posts_jira_url(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_existing(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.sync_marker_posted is True
        assert result.jira_comment_added is True
        assert result.issue_key == "FILING-1234"
        assert result.jira_url == "https://acme.atlassian.net/browse/FILING-1234"
        text = slack.chat_postMessage.call_args.kwargs["text"]
        assert "https://acme.atlassian.net/browse/FILING-1234" in text

    def test_sync_only_does_not_create_jira_issue(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_existing(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert not hasattr(jira, "create_issue") or not jira.create_issue.called

    def test_sync_only_creates_link(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        svc.sync_existing(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        link = store.get_by_issue("FILING-1234")
        assert link is not None

    def test_sync_only_posts_jira_comment_with_permalink(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_existing(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
        )
        comment_text = jira.add_comment.call_args[0][1]
        assert "https://slack.com/archives/C001/p123456" in comment_text
        assert LINK_COMMENT_MARKER in comment_text

    def test_sync_only_posts_minimal_jira_comment_without_permalink(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_existing(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        comment_text = jira.add_comment.call_args[0][1]
        assert LINK_COMMENT_MARKER in comment_text
        assert comment_text == build_initial_link_comment(None)


# ===========================================================================
# 11. Deduplication — initial link
# ===========================================================================

class TestSyncDeduplication:
    def test_duplicate_url_not_posted(self) -> None:
        """If the Jira issue URL is already in the thread, skip posting."""
        slack = _mock_slack(
            existing_messages=[{
                "text": "https://acme.atlassian.net/browse/FILING-1234\nSync [FILING-1234]",
                "ts": "100.0",
            }],
        )
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            transcript="EIT issue found",
        )
        assert result.skipped_marker is True
        assert result.sync_marker_posted is False
        slack.chat_postMessage.assert_not_called()

    def test_duplicate_legacy_marker_not_posted(self) -> None:
        """Backward compat: old Sync [KEY] format also prevents re-posting."""
        slack = _mock_slack(
            existing_messages=[{"text": "Sync [FILING-1234]", "ts": "100.0"}],
        )
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        assert result.skipped_marker is True
        assert result.sync_marker_posted is False

    def test_duplicate_jira_link_comment_not_added(self) -> None:
        existing_comment = build_initial_link_comment(
            "https://slack.com/archives/C001/p123456"
        )
        slack = _mock_slack()
        jira = _mock_jira(
            existing_comments=[_adf_comment(existing_comment, comment_id="500")],
        )
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
            transcript="EIT issue found",
        )
        assert result.skipped_comment is True
        assert result.jira_comment_added is False
        jira.add_comment.assert_not_called()

    def test_both_already_exist(self) -> None:
        existing_comment = build_initial_link_comment(
            "https://slack.com/archives/C001/p123456"
        )
        slack = _mock_slack(
            existing_messages=[{
                "text": "https://acme.atlassian.net/browse/FILING-1234\nSync [FILING-1234]",
                "ts": "100.0",
            }],
        )
        jira = _mock_jira(
            existing_comments=[_adf_comment(existing_comment, comment_id="500")],
        )
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
            permalink="https://slack.com/archives/C001/p123456",
            transcript="EIT issue found",
        )
        assert result.skipped_marker is True
        assert result.skipped_comment is True
        slack.chat_postMessage.assert_not_called()
        jira.add_comment.assert_not_called()


# ===========================================================================
# 12. Slack reply -> Jira comment (two-way sync)
# ===========================================================================

class TestSlackToJiraSync:
    def _setup(self, *, slack_messages=None, jira_comments=None, bot_user_id="BOT1"):
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-100",
            channel_id="C001",
            thread_ts="100.0",
            jira_base_url=JIRA_BASE,
            last_synced_slack_ts="100.0",
        )
        store.save(link)

        slack = _mock_slack(slack_messages)
        jira = _mock_jira(jira_comments)
        svc = SyncService(slack, jira, store, bot_user_id=bot_user_id, jira_base_url=JIRA_BASE)
        return svc, store, slack, jira

    def test_new_slack_reply_synced_to_jira(self) -> None:
        svc, store, slack, jira = self._setup(slack_messages=[
            {"ts": "100.0", "user": "U001", "text": "Thread start"},
            {"ts": "101.0", "user": "U002", "username": "Tony Henriquez",
             "text": "The agency confirmed the filing was accepted."},
        ])

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 1
        jira.add_comment.assert_called_once()
        comment = jira.add_comment.call_args[0][1]
        assert "Tony Henriquez (Slack):" in comment
        assert "The agency confirmed the filing was accepted." in comment

    def test_multiple_new_replies_synced(self) -> None:
        svc, store, slack, jira = self._setup(slack_messages=[
            {"ts": "100.0", "user": "U001", "text": "Thread start"},
            {"ts": "101.0", "user": "U002", "username": "Alice", "text": "First reply"},
            {"ts": "102.0", "user": "U003", "username": "Bob", "text": "Second reply"},
        ])

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 2
        assert jira.add_comment.call_count == 2

    def test_bot_messages_skipped(self) -> None:
        svc, store, slack, jira = self._setup(
            slack_messages=[
                {"ts": "100.0", "user": "U001", "text": "Thread start"},
                {"ts": "101.0", "user": "BOT1",
                 "text": "https://acme.atlassian.net/browse/FILING-100\nSync [FILING-100]"},
                {"ts": "102.0", "user": "U002", "username": "Tony", "text": "Real reply"},
            ],
            bot_user_id="BOT1",
        )

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 1
        assert result.slack_to_jira_skipped >= 1

    def test_jira_url_messages_skipped(self) -> None:
        """Messages containing the Jira issue URL are skipped (not real discussion)."""
        svc, store, slack, jira = self._setup(
            slack_messages=[
                {"ts": "100.0", "user": "U001", "text": "Thread start"},
                {"ts": "101.0", "user": "U999",
                 "text": "https://acme.atlassian.net/browse/FILING-100\nSync [FILING-100]"},
            ],
            bot_user_id=None,
        )

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 0
        assert result.slack_to_jira_skipped >= 1

    def test_legacy_sync_marker_messages_skipped(self) -> None:
        """Even without URL, legacy Sync [KEY] markers are skipped."""
        svc, store, slack, jira = self._setup(
            slack_messages=[
                {"ts": "100.0", "user": "U001", "text": "Thread start"},
                {"ts": "101.0", "user": "U999", "text": "Sync [FILING-100]"},
            ],
            bot_user_id=None,
        )

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 0

    def test_already_synced_messages_not_reprocessed(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-100",
            channel_id="C001",
            thread_ts="100.0",
            last_synced_slack_ts="102.0",
        )
        store.save(link)

        slack = _mock_slack([
            {"ts": "100.0", "user": "U001", "text": "Thread start"},
            {"ts": "101.0", "user": "U002", "username": "Old", "text": "Already synced"},
            {"ts": "102.0", "user": "U003", "username": "Also old", "text": "Also synced"},
            {"ts": "103.0", "user": "U004", "username": "New", "text": "New message"},
        ])
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 1
        comment = jira.add_comment.call_args[0][1]
        assert "New (Slack):" in comment

    def test_updates_last_synced_slack_ts(self) -> None:
        svc, store, slack, jira = self._setup(slack_messages=[
            {"ts": "100.0", "user": "U001", "text": "Thread start"},
            {"ts": "105.0", "user": "U002", "username": "Alice", "text": "Reply"},
        ])

        svc.sync_slack_to_jira("FILING-100")
        link = store.get_by_issue("FILING-100")
        assert link.last_synced_slack_ts == "105.0"

    def test_no_link_returns_error(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        result = svc.sync_slack_to_jira("FILING-999")
        assert len(result.errors) > 0
        assert "No sync link found" in result.errors[0]

    def test_jira_comment_includes_synced_from_slack_marker(self) -> None:
        svc, store, slack, jira = self._setup(slack_messages=[
            {"ts": "100.0", "user": "U001", "text": "Start"},
            {"ts": "101.0", "user": "U002", "username": "Tony", "text": "A reply"},
        ])

        svc.sync_slack_to_jira("FILING-100")
        comment = jira.add_comment.call_args[0][1]
        assert SYNCED_FROM_SLACK_MARKER in comment


# ===========================================================================
# 13. Jira comment -> Slack reply (two-way sync)
# ===========================================================================

class TestJiraToSlackSync:
    def _setup(self, *, jira_comments=None, last_jira_id="500"):
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-200",
            channel_id="C002",
            thread_ts="200.0",
            jira_base_url=JIRA_BASE,
            last_synced_jira_comment_id=last_jira_id,
        )
        store.save(link)

        slack = _mock_slack()
        jira = _mock_jira(jira_comments)
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)
        return svc, store, slack, jira

    def test_new_jira_comment_synced_to_slack(self) -> None:
        svc, store, slack, jira = self._setup(jira_comments=[
            _adf_comment("Old comment", comment_id="500", author="System"),
            _adf_comment(
                "Engineering identified the root cause and deployed a fix.",
                comment_id="501",
                author="Kapil Mohan",
            ),
        ])

        result = svc.sync_jira_to_slack("FILING-200")
        assert result.jira_to_slack_synced == 1
        slack.chat_postMessage.assert_called_once()
        posted_text = slack.chat_postMessage.call_args.kwargs["text"]
        assert "Kapil Mohan (Jira):" in posted_text
        assert "Engineering identified the root cause" in posted_text

    def test_multiple_new_comments_synced(self) -> None:
        svc, store, slack, jira = self._setup(jira_comments=[
            _adf_comment("Old", comment_id="500"),
            _adf_comment("Comment 1", comment_id="501", author="Alice"),
            _adf_comment("Comment 2", comment_id="502", author="Bob"),
        ])

        result = svc.sync_jira_to_slack("FILING-200")
        assert result.jira_to_slack_synced == 2
        assert slack.chat_postMessage.call_count == 2

    def test_synced_from_slack_comments_skipped(self) -> None:
        svc, store, slack, jira = self._setup(jira_comments=[
            _adf_comment("Old", comment_id="500"),
            _adf_comment(
                f"Tony (Slack): Some reply\n{SYNCED_FROM_SLACK_MARKER}",
                comment_id="501",
                author="bot-user",
            ),
        ])

        result = svc.sync_jira_to_slack("FILING-200")
        assert result.jira_to_slack_synced == 0
        assert result.jira_to_slack_skipped == 1
        slack.chat_postMessage.assert_not_called()

    def test_initial_link_comment_skipped(self) -> None:
        link_comment = build_initial_link_comment(
            "https://slack.com/archives/C002/p200000"
        )
        svc, store, slack, jira = self._setup(jira_comments=[
            _adf_comment("Old", comment_id="500"),
            _adf_comment(link_comment, comment_id="501", author="bot-user"),
        ])

        result = svc.sync_jira_to_slack("FILING-200")
        assert result.jira_to_slack_synced == 0
        assert result.jira_to_slack_skipped == 1

    def test_already_synced_comments_not_reprocessed(self) -> None:
        svc, store, slack, jira = self._setup(
            jira_comments=[
                _adf_comment("Already synced", comment_id="500"),
                _adf_comment("New comment", comment_id="501", author="Kapil"),
            ],
            last_jira_id="500",
        )

        result = svc.sync_jira_to_slack("FILING-200")
        assert result.jira_to_slack_synced == 1
        posted_text = slack.chat_postMessage.call_args.kwargs["text"]
        assert "Kapil (Jira):" in posted_text

    def test_updates_last_synced_jira_comment_id(self) -> None:
        svc, store, slack, jira = self._setup(jira_comments=[
            _adf_comment("Old", comment_id="500"),
            _adf_comment("New", comment_id="501", author="Alice"),
        ])

        svc.sync_jira_to_slack("FILING-200")
        link = store.get_by_issue("FILING-200")
        assert link.last_synced_jira_comment_id == "501"

    def test_no_link_returns_error(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        result = svc.sync_jira_to_slack("FILING-999")
        assert len(result.errors) > 0


# ===========================================================================
# 14. Infinite loop prevention
# ===========================================================================

class TestLoopPrevention:
    def test_slack_bot_message_not_synced_back_to_jira(self) -> None:
        """A Jira->Slack synced message (posted by bot) must not sync back to Jira."""
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-300",
            channel_id="C003",
            thread_ts="300.0",
            last_synced_slack_ts="300.0",
        )
        store.save(link)

        slack = _mock_slack([
            {"ts": "300.0", "user": "U001", "text": "Thread start"},
            {"ts": "301.0", "user": "BOT1", "text": "Kapil Mohan (Jira): Some update"},
        ])
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result = svc.sync_slack_to_jira("FILING-300")
        assert result.slack_to_jira_synced == 0
        assert result.slack_to_jira_skipped >= 1
        jira.add_comment.assert_not_called()

    def test_jira_synced_from_slack_comment_not_synced_back_to_slack(self) -> None:
        """A Slack->Jira synced comment must not sync back to Slack."""
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-300",
            channel_id="C003",
            thread_ts="300.0",
            last_synced_jira_comment_id="600",
        )
        store.save(link)

        jira_comments = [
            _adf_comment("Previous", comment_id="600"),
            _adf_comment(
                f"Tony (Slack): Original slack message\n{SYNCED_FROM_SLACK_MARKER}",
                comment_id="601",
                author="sync-bot",
            ),
        ]
        slack = _mock_slack()
        jira = _mock_jira(jira_comments)
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result = svc.sync_jira_to_slack("FILING-300")
        assert result.jira_to_slack_synced == 0
        assert result.jira_to_slack_skipped == 1
        slack.chat_postMessage.assert_not_called()

    def test_full_round_trip_no_infinite_loop(self) -> None:
        """Simulate: human Slack msg -> Jira comment -> verify no Slack re-post."""
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-400",
            channel_id="C004",
            thread_ts="400.0",
            last_synced_slack_ts="400.0",
            last_synced_jira_comment_id="700",
        )
        store.save(link)

        slack = _mock_slack([
            {"ts": "400.0", "user": "U001", "text": "Start"},
            {"ts": "401.0", "user": "U002", "username": "Tony", "text": "Human message"},
        ])
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        s2j = svc.sync_slack_to_jira("FILING-400")
        assert s2j.slack_to_jira_synced == 1

        synced_comment_text = jira.add_comment.call_args[0][1]
        assert SYNCED_FROM_SLACK_MARKER in synced_comment_text

        jira.get_comments.return_value = [
            _adf_comment("Previous", comment_id="700"),
            _adf_comment(synced_comment_text, comment_id="701", author="sync-bot"),
        ]

        j2s = svc.sync_jira_to_slack("FILING-400")
        assert j2s.jira_to_slack_synced == 0
        assert j2s.jira_to_slack_skipped == 1
        slack.chat_postMessage.assert_not_called()

    def test_full_round_trip_jira_to_slack_no_infinite_loop(self) -> None:
        """Simulate: human Jira comment -> Slack post (by bot) -> verify no Jira re-post."""
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-500",
            channel_id="C005",
            thread_ts="500.0",
            last_synced_slack_ts="500.0",
            last_synced_jira_comment_id="800",
        )
        store.save(link)

        jira_comments = [
            _adf_comment("Previous", comment_id="800"),
            _adf_comment("Human Jira comment", comment_id="801", author="Kapil"),
        ]
        slack = _mock_slack()
        jira = _mock_jira(jira_comments)
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        j2s = svc.sync_jira_to_slack("FILING-500")
        assert j2s.jira_to_slack_synced == 1

        slack.conversations_replies.return_value = {
            "messages": [
                {"ts": "500.0", "user": "U001", "text": "Start"},
                {"ts": "501.0", "user": "BOT1",
                 "text": "Kapil (Jira): Human Jira comment"},
            ],
        }

        s2j = svc.sync_slack_to_jira("FILING-500")
        assert s2j.slack_to_jira_synced == 0
        assert s2j.slack_to_jira_skipped >= 1

    def test_jira_url_message_not_synced_to_jira(self) -> None:
        """The Jira URL posted by the bot should not become a Jira comment."""
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-300",
            channel_id="C003",
            thread_ts="300.0",
            last_synced_slack_ts="300.0",
        )
        store.save(link)

        slack = _mock_slack([
            {"ts": "300.0", "user": "U001", "text": "Thread start"},
            {"ts": "301.0", "user": "U999",
             "text": "https://acme.atlassian.net/browse/FILING-300\nSync [FILING-300]"},
        ])
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, bot_user_id=None, jira_base_url=JIRA_BASE)

        result = svc.sync_slack_to_jira("FILING-300")
        assert result.slack_to_jira_synced == 0
        jira.add_comment.assert_not_called()


# ===========================================================================
# 15. Duplicate prevention in continuous sync
# ===========================================================================

class TestContinuousSyncDeduplication:
    def test_running_sync_twice_does_not_duplicate(self) -> None:
        """Running sync twice should not re-sync already-synced messages."""
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-600",
            channel_id="C006",
            thread_ts="600.0",
            last_synced_slack_ts="600.0",
        )
        store.save(link)

        messages = [
            {"ts": "600.0", "user": "U001", "text": "Start"},
            {"ts": "601.0", "user": "U002", "username": "Alice", "text": "Reply 1"},
        ]
        slack = _mock_slack(messages)
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result1 = svc.sync_slack_to_jira("FILING-600")
        assert result1.slack_to_jira_synced == 1

        result2 = svc.sync_slack_to_jira("FILING-600")
        assert result2.slack_to_jira_synced == 0

    def test_running_jira_sync_twice_does_not_duplicate(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-700",
            channel_id="C007",
            thread_ts="700.0",
            last_synced_jira_comment_id="900",
        )
        store.save(link)

        comments = [
            _adf_comment("Old", comment_id="900"),
            _adf_comment("New", comment_id="901", author="Kapil"),
        ]
        slack = _mock_slack()
        jira = _mock_jira(comments)
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result1 = svc.sync_jira_to_slack("FILING-700")
        assert result1.jira_to_slack_synced == 1

        result2 = svc.sync_jira_to_slack("FILING-700")
        assert result2.jira_to_slack_synced == 0


# ===========================================================================
# 16. sync_all convenience method
# ===========================================================================

class TestSyncAll:
    def test_runs_both_directions(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-800",
            channel_id="C008",
            thread_ts="800.0",
            last_synced_slack_ts="800.0",
            last_synced_jira_comment_id="1000",
        )
        store.save(link)

        slack = _mock_slack([
            {"ts": "800.0", "user": "U001", "text": "Start"},
            {"ts": "801.0", "user": "U002", "username": "Alice", "text": "Slack reply"},
        ])
        jira = _mock_jira([
            _adf_comment("Old", comment_id="1000"),
            _adf_comment("Jira comment", comment_id="1001", author="Kapil"),
        ])
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        s2j, j2s = svc.sync_all("FILING-800")
        assert s2j.slack_to_jira_synced == 1
        assert j2s.jira_to_slack_synced == 1


# ===========================================================================
# 17. get_link / get_link_by_thread
# ===========================================================================

class TestGetLink:
    def test_get_link_by_issue_key(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        link = svc.get_link("FILING-1234")
        assert link is not None
        assert link.issue_key == "FILING-1234"

    def test_get_link_by_thread(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        link = svc.get_link_by_thread("C001", "123.456")
        assert link is not None
        assert link.issue_key == "FILING-1234"

    def test_get_link_returns_none_when_not_found(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        assert svc.get_link("FILING-999") is None
        assert svc.get_link_by_thread("C999", "0.0") is None


# ===========================================================================
# 18. Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_slack_api_failure_during_link(self) -> None:
        slack = _mock_slack()
        slack.conversations_replies.side_effect = Exception("API error")
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="123.456",
        )
        assert result.sync_marker_posted is True
        assert result.jira_comment_added is True

    def test_jira_api_failure_during_slack_to_jira(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-100",
            channel_id="C001",
            thread_ts="100.0",
            last_synced_slack_ts="100.0",
        )
        store.save(link)

        slack = _mock_slack([
            {"ts": "100.0", "user": "U001", "text": "Start"},
            {"ts": "101.0", "user": "U002", "username": "Tony", "text": "Reply"},
        ])
        jira = _mock_jira()
        jira.add_comment.side_effect = Exception("Jira API down")
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 0
        assert len(result.errors) == 1

    def test_empty_thread_no_errors(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-100",
            channel_id="C001",
            thread_ts="100.0",
            last_synced_slack_ts="100.0",
        )
        store.save(link)

        slack = _mock_slack([])
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result = svc.sync_slack_to_jira("FILING-100")
        assert result.slack_to_jira_synced == 0
        assert len(result.errors) == 0

    def test_empty_jira_comments_no_errors(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-100",
            channel_id="C001",
            thread_ts="100.0",
            last_synced_jira_comment_id=None,
        )
        store.save(link)

        slack = _mock_slack()
        jira = _mock_jira([])
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        result = svc.sync_jira_to_slack("FILING-100")
        assert result.jira_to_slack_synced == 0
        assert len(result.errors) == 0

    def test_user_profile_real_name_used_in_slack_to_jira(self) -> None:
        store = InMemorySyncLinkStore()
        link = SyncLink(
            issue_key="FILING-100",
            channel_id="C001",
            thread_ts="100.0",
            last_synced_slack_ts="100.0",
        )
        store.save(link)

        slack = _mock_slack([
            {"ts": "100.0", "user": "U001", "text": "Start"},
            {"ts": "101.0", "user": "U002",
             "user_profile": {"real_name": "Tony Henriquez"},
             "text": "Message with profile"},
        ])
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, bot_user_id="BOT1", jira_base_url=JIRA_BASE)

        svc.sync_slack_to_jira("FILING-100")
        comment = jira.add_comment.call_args[0][1]
        assert "Tony Henriquez (Slack):" in comment


# ===========================================================================
# 19. Native Sync Thread investigation
# ===========================================================================

class TestNativeSyncThreadFallback:
    """Verify the bot handles the absence of a native Sync Thread API correctly."""

    def test_posts_jira_url_for_native_unfurl(self) -> None:
        """The Jira URL must be posted so Jira Cloud for Slack can unfurl a card."""
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-6152",
            channel="C001",
            thread_ts="100.0",
        )
        posted_text = slack.chat_postMessage.call_args.kwargs["text"]
        assert "https://acme.atlassian.net/browse/FILING-6152" in posted_text

    def test_custom_sync_still_works_when_native_unavailable(self) -> None:
        """Two-way sync must function even though native Sync Thread cannot be triggered."""
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-6152",
            channel="C001",
            thread_ts="100.0",
        )
        link = store.get_by_issue("FILING-6152")
        assert link is not None

        slack.conversations_replies.return_value = {
            "messages": [
                {"ts": "100.0", "user": "U001", "text": "Start"},
                {"ts": "101.0", "user": "U002", "username": "Tony",
                 "text": "New discussion point"},
            ],
        }
        result = svc.sync_slack_to_jira("FILING-6152")
        assert result.slack_to_jira_synced == 1

    def test_sync_marker_url_first_line_is_valid_url(self) -> None:
        """The first line of the sync marker must be a valid browsable URL."""
        marker = build_sync_marker("FILING-1234", JIRA_BASE)
        first_line = marker.split("\n")[0]
        assert first_line.startswith("https://")
        assert "/browse/FILING-1234" in first_line

    def test_jira_base_url_stored_in_link(self) -> None:
        store = InMemorySyncLinkStore()
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, store, jira_base_url=JIRA_BASE)

        svc.sync_after_creation(
            issue_key="FILING-1234",
            channel="C001",
            thread_ts="100.0",
        )
        link = store.get_by_issue("FILING-1234")
        assert link.jira_base_url == JIRA_BASE

    def test_result_contains_jira_url(self) -> None:
        slack = _mock_slack()
        jira = _mock_jira()
        svc = SyncService(slack, jira, jira_base_url=JIRA_BASE)

        result = svc.sync_after_creation(
            issue_key="FILING-6152",
            channel="C001",
            thread_ts="100.0",
        )
        assert result.jira_url == "https://acme.atlassian.net/browse/FILING-6152"
