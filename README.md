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

## Product rules (implementation roadmap)

- **No Jira ticket creation** without explicit Slack confirmation (e.g. button).
- **`@claude-filings sync this thread to FILING-1234`:** append thread content to that issue only; never create a ticket or show create confirmation.
- After create: post `Sync [FILING-KEY]` back in the thread.

## Roadmap

| Phase | Scope |
|-------|--------|
| **1** | Scaffolding: `pyproject.toml`, packages, stub `main`, `.env.example`, README, smoke tests |
| **2** | Pydantic models (`FilingIssueDraft`, etc.), `AnthropicClient.complete_json`, prompts, unit tests with mocks |
| **3** | Jira client (create in FILING, labels, parent epic), sync-as-comment; `IntakeService` / `SyncService` |
| **4** | Bolt `app_mention` in thread, confirmation blocks + action handlers, thread fetch, end-to-end tests with mocks |

## License

Proprietary / internal — add a license file if you open-source this repo.
