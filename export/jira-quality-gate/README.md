# Jira Quality Gate — TaxOps Governance Automation

Monitors Jira **PF / Ops - Customer Task** tickets and posts Slack alerts via Zapier webhooks.

## Scripts (A1–A9)

| Script | Schedule | Purpose |
|--------|----------|---------|
| A1 | Polling | Waiting for Ops accountability |
| A2 | Polling | Quality gate field validation |
| A3 | Polling | Label quadrant validation |
| A4 | Polling | Sign-off mismatch |
| A5 | Daily 9 AM UTC | SLA labels (no Slack) |
| A6 | Mon 16:00 UTC | Weekly exec digest |
| A7 | Polling | New scope in comments |
| A8 | Polling | Auto `us-taxops-ticket` label |
| A9 | Polling | Bad-ticket notifier |

Polling runs **Mon–Fri every 15 min** via `run_polling_suite.sh` (all scripts in one job; fails the workflow if any script errors).

## GitHub Secrets

| Secret | Required |
|--------|----------|
| `JIRA_EMAIL` | Yes |
| `JIRA_API_TOKEN` | Yes |
| `SLACK_WEBHOOK_OPS` | Yes (Zapier Catch Hook → `#taxops`) |
| `SLACK_WEBHOOK_EXEC` | Yes (weekly digest Zap) |
| `JIRA_BASE_URL` | Optional (default `https://rippling.atlassian.net`) |
| `RANA_SLACK_UID` | Optional |
| `LEAD_NAMES_JSON` | Optional (unused by scripts today) |

## Zapier threading

See [ZAPIER_SLACK_THREADING.md](ZAPIER_SLACK_THREADING.md). Ticket alerts send `message` + `ticket_key` in JSON.

## Local run

```bash
pip install -r requirements.txt
export JIRA_EMAIL=... JIRA_API_TOKEN=... SLACK_WEBHOOK_OPS=... SLACK_WEBHOOK_EXEC=...
python a2_quality_gate.py
```

## Migrated from

Originally lived in `thenriquezrippling/filings-and-payments` under `taxops/`. Disable workflows in that repo after cutover to avoid duplicate runs.
