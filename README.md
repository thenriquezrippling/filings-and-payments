# Tax Ops filing intake Slack bot

Standalone Python bot for Tax Ops **filing** issue intake: read a Slack thread, infer Jira fields with an LLM, confirm in Slack, then create a ticket in project **FILING** (or sync thread text to an existing issue).

Requires **Python 3.11+** (`requires-python` in `pyproject.toml`).

## Layout

- `src/tax_ops_filing_bot/slack/` — Slack Bolt app, `app_mention` handler, Block Kit confirmation UI, thread fetching
- `src/tax_ops_filing_bot/jira/` — Jira Cloud REST v3 client (create issue, add comment, transition, labels)
- `src/tax_ops_filing_bot/llm/` — Anthropic wrapper with retry + JSON-to-Pydantic parsing, filing-specific prompts
- `src/tax_ops_filing_bot/services/` — `IntakeService` (thread → LLM → Jira) and `SyncService` (thread → comment)
- `src/tax_ops_filing_bot/models/` — Pydantic schemas: `FilingIssueDraft`, `ThreadContext`, `SyncRequest`, enums

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with real credentials
```

Run the bot:

```bash
tax-ops-filing-bot
# or: python -m tax_ops_filing_bot
```

Run tests:

```bash
pytest
```

## How it works

1. **Mention the bot in a Slack thread** — the bot reads all messages in the thread.
2. **LLM extraction** — Claude analyzes the thread and produces a structured `FilingIssueDraft` with summary, description, category, agency, priority, labels, affected entities, and suggested DRI.
3. **Confirmation** — the bot posts a Block Kit card in the thread with the draft details and "Create Ticket" / "Cancel" buttons.
4. **Jira creation** — on confirmation, a FILING issue is created with all extracted fields and a link back to the Slack thread.
5. **Sync mode** — mention the bot with `sync this thread to FILING-XXXX` to append thread content as a comment on an existing issue.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot user OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | For Socket Mode | App-level token with `connections:write` |
| `JIRA_BASE_URL` | Yes | Cloud site URL, e.g. `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | Yes | Account email for API basic auth |
| `JIRA_API_TOKEN` | Yes | [API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_PROJECT_KEY` | Optional | Default `FILING` |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `SLACK_BOT_USER_ID` | Optional | Bot member ID for mention parsing |

## Slack app setup

1. Create a Slack app; add **Bot Token Scopes**: `app_mentions:read`, `channels:history`, `groups:history`, `im:history`, `mpim:history`, `chat:write`, `users:read`.
2. Install the app to the workspace; copy `SLACK_BOT_TOKEN`.
3. **Socket Mode:** enable Socket Mode, create an app-level token with `connections:write`, set `SLACK_APP_TOKEN`.
4. **HTTP mode (alternative):** enable Interactivity and Event Subscriptions with a public HTTPS endpoint.

## Product rules

- **No Jira ticket creation** without explicit Slack confirmation (button click).
- **`@bot sync this thread to FILING-1234`:** append thread content to that issue only; never create a ticket or show create confirmation.
- After create: post `Created FILING-KEY: summary` back in the thread with a Jira link.

## Issue categories

The LLM maps threads to these filing-specific categories:

| Category | Description |
|----------|-------------|
| `missing_employee_data` | Blank SSNs, missing names, EFDS sync gaps |
| `incorrect_wages` | SWWL $0, negative excess wages |
| `peo_reconciliation` | PEO/RPEO wage aggregation mismatches |
| `account_sync` | Missing FEINs, CAAS gaps, account numbers |
| `payment_issue` | Payment diffs, delays, check issuance |
| `efile_blocked` | IRS e-file blocked, ATS gateway issues |
| `agency_change` | Portal changes, format changes, TPA auth |
| `tax_config` | Recon rate errors, FF config overrides |
| `other` | Anything else |

## License

Proprietary / internal — add a license file if you open-source this repo.
