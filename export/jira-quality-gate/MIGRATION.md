# Cutover checklist: filings-and-payments → jira-quality-gate

## 1. Create / open the new repo

https://github.com/rippling-foundry/jira-quality-gate

Ensure the Cloud Agent or your account can **push** to `rippling-foundry`.

## 2. Push this export (one-time)

From a machine with access to both repos:

```bash
cd export/jira-quality-gate   # or clone filings-and-payments and use this path
git init
git branch -M main
git remote add origin git@github.com:rippling-foundry/jira-quality-gate.git
git add -A
git commit -m "feat: TaxOps Jira governance automation suite"
git push -u origin main
```

Or: copy files from `export/jira-quality-gate/` into the new repo via GitHub UI.

## 3. GitHub Secrets (new repo)

Copy from `filings-and-payments` → Settings → Secrets:

- `JIRA_EMAIL`
- `JIRA_API_TOKEN`
- `SLACK_WEBHOOK_OPS`
- `SLACK_WEBHOOK_EXEC`
- `RANA_SLACK_UID` (optional)
- `JIRA_BASE_URL` (optional)
- `LEAD_NAMES_JSON` (optional)

**Zapier URLs stay the same** — no Zap changes required.

## 4. Enable workflows

Actions → enable the three workflows → run **TaxOps Polling** via `workflow_dispatch` once.

## 5. Disable old repo (avoid duplicate alerts)

In **thenriquezrippling/filings-and-payments**, delete or disable:

- `.github/workflows/taxops-polling.yml`
- `.github/workflows/taxops-daily.yml`
- `.github/workflows/taxops-weekly.yml`

Optional: add a note in `taxops/README.md` pointing to the new repo.

## 6. Weekly digest note

A6 commits `wbr_history.json` back to the repo. Ensure branch protection on `main` allows `github-actions` to push, or adjust the weekly workflow.

## Layout change

Scripts live at **repo root** (not `taxops/`). Workflows use `pip install -r requirements.txt` and `bash run_polling_suite.sh` at root.
