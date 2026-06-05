# Zapier ↔ Slack threading (TaxOps webhooks)

GitHub Actions Python scripts **do not** call Slack’s API directly. They `POST` JSON to your **Zapier Catch Hook** URL(s). Threading only works if the Zap **stores** the parent message’s Slack timestamp and **reuses** it on follow-up posts.

## Payload from Python (`common.slack_post`)

Every ticket-scoped alert sends:

```json
{
  "message": "<Slack-formatted text>",
  "ticket_key": "PF-12345"
}
```

`ticket_key` is always the Jira issue key (same string every time for that ticket).  
Non-ticket posts (e.g. `post_error`) send only `message` (no `ticket_key`).

The weekly digest (A6) uses a **different** JSON shape and the **exec** webhook — not this threading model.

## Why you see a new top-level message each time

Almost always one of these in Zapier:

1. **Path order / filters** — The Zap should run something like:
   - **Path A (reply):** “We already have a `thread_ts` stored for this `ticket_key`” → Slack step posts **in thread** using that `thread_ts`.
   - **Path B (new parent):** “No stored `thread_ts` for this `ticket_key`” → post **to channel**, then **save** the returned `ts` keyed by `ticket_key`.
   If Path B always runs (lookup never matches), every alert starts a new parent message.

2. **Storage key mismatch** — The step that **writes** the Slack `ts` must use the **same** key string as the step that **reads** it (e.g. both use `ticket_key` from the Catch Hook). Typos, extra spaces, different formatter output (`PF-123` vs `pf-123`), or using a different field name will make every request look “new”.

3. **Wrong value stored for threading** — For the **first** parent post in a channel, Slack’s `thread_ts` for replies is that message’s **`ts`**. The Zap must store that **`ts`** (from the Slack response) and pass it as **`thread_ts`** on the next “reply” action. Storing a different field or the wrong `ts` breaks threading.

4. **Slack step not wired to thread** — In “Send channel message”, the **Thread / Reply / thread_ts** input must be mapped from **Storage** (or Zapier Tables), not left empty.

5. **Multiple Zaps or duplicate triggers** — Two Zaps using the same idea but only one updating Storage can cause inconsistent behavior. One Zap per Catch Hook URL is easiest to reason about.

## How to confirm in Zapier

1. Open the Zap tied to **`SLACK_WEBHOOK_OPS`** (same URL as in GitHub Actions secrets).
2. **Catch Hook → Test** (or **Task history** for a real run) and confirm **`ticket_key`** appears in the incoming data exactly as `PF-…`.
3. Trace **Paths** after the trigger: which path runs for a **second** alert on the same ticket?
4. Open the **Slack** step on the “reply” path — confirm **`thread_ts`** (or equivalent) is filled from **Storage Get** (or equivalent), not blank.
5. Open the **Storage Set** (or equivalent) on the “new message” path — confirm it saves using **`ticket_key`** and saves the **parent message `ts`** from Slack’s response.

## Quick Zap layout (reference)

```text
Catch Hook (JSON: message, ticket_key?)
    → Paths
        Path A: Storage has key == ticket_key  → Slack: post with thread_ts = stored ts
        Path B: else                            → Slack: post to channel → Storage: set ticket_key → message ts
```

Adjust names to match your Zap (Storage vs Code vs Tables). The **logic** is what matters.

If everything above matches and it still splits threads, compare **two Task History entries** for the same `ticket_key` and see whether Path A or B ran and what value was read/written in Storage.
