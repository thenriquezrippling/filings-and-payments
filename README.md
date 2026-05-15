# Tax Ops filing intake Slack bot

Standalone Python bot for Tax Ops **filing** issue intake: read a Slack thread, infer Jira fields with an LLM, confirm in Slack, then create a ticket in project **FILING** (or sync thread text to an existing issue).

**Phase 1 (current):** repository scaffolding only — packaging, module layout, stub entrypoint, and smoke tests. No Bolt listeners, Jira calls, or live LLM yet.

Requires **Python 3.11+** (`requires-python` in `pyproject.toml`).

## Layout

- `src/tax_ops_filing_bot/slack/` — Slack Bolt app and Block Kit (Phase 4)
- `src/tax_ops_filing_bot/jira/` — Atlassian REST client (Phase 3)
- `src/tax_ops_filing_bot/llm/` — Anthropic wrapper and prompts (Phase 2)
- `src/tax_ops_filing_bot/services/` — Intake and sync orchestration (Phases 3–4)
- `src/tax_ops_filing_bot/models/` — Pydantic schemas for structured outputs (Phase 2)

## Setup

```bash
cd filing-jira-bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with real credentials
```

Run the scaffold entrypoint:

```bash
tax-ops-filing-bot
# or: python -m tax_ops_filing_bot
```

Run tests:

```bash
pytest
```

## Environment variables

| Variable | Required (Phase 1) | Description |
|----------|-------------------|-------------|
| `SLACK_BOT_TOKEN` | For Slack (later) | Bot user OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | If using Socket Mode | App-level token with `connections:write` |
| `JIRA_BASE_URL` | For Jira (later) | Cloud site URL, e.g. `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | For Jira (later) | Account email for API basic auth |
| `JIRA_API_TOKEN` | For Jira (later) | [API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_PROJECT_KEY` | Optional | Default `FILING` |
| `ANTHROPIC_API_KEY` | For LLM (later) | Anthropic API key |
| `SLACK_BOT_USER_ID` | Optional | Bot member ID for mention parsing |

## Slack app (outline)

1. Create a Slack app; add **Bot Token Scopes** as needed later (e.g. `app_mentions:read`, `channels:history`, `groups:history`, `im:history`, `mpim:history`, `chat:write`, `users:read`).
2. Install the app to the workspace; copy `SLACK_BOT_TOKEN`.
3. **Socket Mode:** enable Socket Mode, create an app-level token with `connections:write`, set `SLACK_APP_TOKEN`. This is the simplest way to run the bot without a public URL.
4. **HTTP mode (alternative):** enable Interactivity and Event Subscriptions with a public HTTPS endpoint; use the signing secret and omit `SLACK_APP_TOKEN` in favor of the Bolt HTTP adapter.

## Jira (outline)

Use Jira Cloud REST API v3 with email + API token (Basic auth). For create metadata and parent/epic fields, use [GET issue create metadata](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-createmeta-get) for project `FILING` and document required field IDs for your project type (next-gen `parent` vs classic Epic Link).

## Two-way Slack ↔ Jira synchronization

The `SyncService` in `services/sync_service.py` provides persistent, bidirectional synchronization between Slack threads and Jira issues in the FILING project.

### Native Sync Thread — Investigation Results (May 2026)

**The Jira Cloud Slack app's native "Sync Thread" button CANNOT be triggered programmatically.** This is not a custom `Sync [FILING-KEY]` marker — we are referring to the actual native Jira Cloud Slack app feature that appears on the unfurl card when a Jira URL is posted.

**Investigated avenues (all negative):**

| Approach | Result |
|----------|--------|
| Atlassian REST API | No endpoint for triggering Sync Thread |
| Atlassian MCP tools | Only issue CRUD available (createJiraIssue, editJiraIssue, addCommentToJiraIssue, etc.) |
| Slack connector catalog (`jira.cloud`) | Only exposes `create_issue` and `edit_issue` |
| Atlassian Forge / Connect apps | No module, hook, or event to invoke native Sync Thread |
| Community requests (JRACLOUD-97440, JRACLOUD-97607) | All unresolved feature requests as of May 2026 |

**Critical limitation — bot-posted URLs excluded:**

Even posting the Jira URL from our bot **does NOT activate native Sync Thread**. Per [JRACLOUD-97440](https://jira.atlassian.com/browse/JRACLOUD-97440), messages posted by bot users show an "Assign" button on the unfurl card instead of "Sync Thread". The native sync feature only works when a **human** manually pastes a Jira URL.

**Additional context:**
- The native Sync Thread was temporarily disabled by Atlassian (Oct 2025) for improvements.
- Re-enabled in phases (Nov 2025), still rolling out to tenants as of April 2026.
- Only works in Channels (not DMs or group chats).
- Availability per-tenant requires contacting Atlassian directly (mravishankar@atlassian.com per community posts).

**Conclusion:** Native Sync Thread is a manual UI-only action. No programmatic trigger exists. Custom two-way sync is the only viable approach for bot-driven synchronization.

### Recommended approach (implemented)

Since native sync cannot be triggered programmatically, this bot implements custom two-way sync that mirrors the native behavior:

1. **Post the Jira issue URL** in the Slack thread — this causes the Jira Cloud app to unfurl a rich card (if installed and enabled for the tenant), giving users visibility into the linked issue.
2. **Run custom bidirectional sync** — Slack replies become Jira comments, Jira comments become Slack thread replies, with full loop prevention and deduplication.

### How to link a thread

There are two ways to establish a link:

1. **Ticket creation flow** — when a new Jira ticket is created from a Slack thread, the bot automatically calls `sync_after_creation()`, which posts the Jira issue URL (e.g. `https://your-domain.atlassian.net/browse/FILING-6152`) in the thread and adds a minimal Jira comment with the Slack permalink.

2. **Sync-only command** — a user sends `sync this thread to FILING-1234` (or `@bot sync this thread to FILING-1234`). The bot calls `sync_existing()`, which links the thread to the existing issue without creating a new ticket.

Both flows create a `SyncLink` record that stores the Jira issue key, Slack channel ID, thread timestamp, permalink, Jira base URL, and sync cursors.

### How two-way sync works

Once a link is established, the sync engine runs in two directions:

**Slack → Jira:** `sync_slack_to_jira(issue_key)` fetches new replies in the linked Slack thread (after the last synced timestamp) and creates a Jira comment for each:

```
Tony Henriquez (Slack): The agency confirmed the filing was accepted.
```

**Jira → Slack:** `sync_jira_to_slack(issue_key)` fetches new Jira comments (after the last synced comment ID) and posts each into the linked Slack thread:

```
Kapil Mohan (Jira): Engineering identified the root cause and deployed a fix.
```

The `sync_all(issue_key)` convenience method runs both directions in a single call.

### How loop prevention works

The sync engine prevents infinite Slack ↔ Jira loops through four mechanisms:

1. **Bot user filtering** — Slack messages posted by the bot (identified by `bot_user_id`) are skipped during Slack→Jira sync. This covers Jira→Slack synced messages and the Jira URL post itself.

2. **Jira URL / sync marker filtering** — messages containing a Jira issue URL (`/browse/...`) or `Sync [KEY]` are skipped during Slack→Jira sync, even if not posted by the bot user.

3. **Synced-from-Slack marker** — every Jira comment created by the Slack→Jira sync includes a `[synced-from-slack]` suffix. The Jira→Slack sync skips any comment containing this marker.

4. **Initial link comment filtering** — the initial Jira link comment ("Linked Slack thread: ...") is skipped during Jira→Slack sync.

Deduplication is also enforced:
- The Jira issue URL is checked before posting (no duplicate URL messages).
- Legacy `Sync [FILING-KEY]` markers are also detected for backward compatibility.
- Link comments are checked before adding (no duplicate initial Jira comments).
- `last_synced_slack_ts` and `last_synced_jira_comment_id` cursors prevent reprocessing.

### Operational examples

**Initial link after ticket creation:**
```
Slack thread:  ... operational discussion ...
Bot posts:     https://your-domain.atlassian.net/browse/FILING-6152
               Sync [FILING-6152]
Jira comment:  Linked Slack thread: https://slack.com/archives/C001/p123456
               Linked Slack thread for ongoing discussion and updates.
```

The Jira issue URL triggers the Jira Cloud Slack app to unfurl a native card showing the issue summary, status, and assignee.

**Ongoing Slack reply synced to Jira:**
```
Slack (Tony):  "The agency confirmed the filing was accepted."
  → Jira comment: "Tony Henriquez (Slack): The agency confirmed the filing was accepted."
```

**Ongoing Jira comment synced to Slack:**
```
Jira (Kapil):  "Engineering identified the root cause and deployed a fix."
  → Slack reply: "Kapil Mohan (Jira): Engineering identified the root cause and deployed a fix."
```

### Metadata storage

Each `SyncLink` stores:

| Field | Description |
|-------|-------------|
| `issue_key` | Jira issue key (e.g. `FILING-6152`) |
| `channel_id` | Slack channel ID |
| `thread_ts` | Slack thread timestamp |
| `permalink` | Slack thread permalink (optional) |
| `jira_base_url` | Jira Cloud site URL (for building browse URLs) |
| `last_synced_slack_ts` | Timestamp of last synced Slack message |
| `last_synced_jira_comment_id` | ID of last synced Jira comment |

The default `InMemorySyncLinkStore` is suitable for testing and single-process deployments. Swap in a database-backed implementation of the `SyncLinkStore` protocol for production persistence.

## Product rules (implementation roadmap)

- **No Jira ticket creation** without explicit Slack confirmation (e.g. button).
- **`@claude-filings sync this thread to FILING-1234`:** append thread content to that issue only; never create a ticket or show create confirmation.
- After create: post the Jira issue URL back in the thread (native card unfurl), establish two-way sync.

## Roadmap

| Phase | Scope |
|-------|--------|
| **1** | Scaffolding: `pyproject.toml`, packages, stub `main`, `.env.example`, README, smoke tests |
| **2** | Pydantic models (`FilingIssueDraft`, etc.), `AnthropicClient.complete_json`, prompts, unit tests with mocks |
| **3** | Jira client (create in FILING, labels, parent epic), sync-as-comment; `IntakeService` / `SyncService` |
| **4** | Bolt `app_mention` in thread, confirmation blocks + action handlers, thread fetch, end-to-end tests with mocks |

## License

Proprietary / internal — add a license file if you open-source this repo.
