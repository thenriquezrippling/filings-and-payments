"""
A9 - Bad Ticket Notifier
Polling every 15 min (Mon–Fri).

Watches for tickets with the `bad-ticket` label.
Tags reporter + region lead + @us-taxops-leaders on each reminder until resolved.

Reminders repeat every REMINDER_HOURS while the ticket stays open with `bad-ticket`.
Stops automatically when the ticket is resolved/closed (dropped from open JQL).

Dedup: AUTO_FLAG:BAD_TICKET comment timestamp gates repeat Slack alerts.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

BAD_TICKET_FLAG = "AUTO_FLAG:BAD_TICKET"
REMINDER_HOURS  = 24


def _should_notify(issue_key):
    """Return (notify, is_first_alert)."""
    since = hours_since_comment_matching(issue_key, BAD_TICKET_FLAG)
    if since is None:
        return True, True
    return since >= REMINDER_HOURS, False


def run():
    issues = jira_search(
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} AND {JQL_TAXOPS_OWNED} AND labels = "bad-ticket"',
        fields=COMMON_FIELDS,
    )
    print(f"[A9] {len(issues)} open tickets with bad-ticket label")

    notified = 0
    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        status  = (fields.get("status") or {}).get("name", "Unknown")
        labels  = get_labels(issue)
        is_peo  = "e2e-peo" in labels
        rep_tag  = reporter_tag_for(issue)
        lead_tag = lead_tag_for(labels, is_peo)

        try:
            should_notify, is_first = _should_notify(key)
            if not should_notify:
                continue

            if is_first:
                add_comment(key,
                    f"{BAD_TICKET_FLAG} — Bad Ticket notification sent.\n"
                    f"This ticket has the `bad-ticket` label. Reminders will repeat every "
                    f"{REMINDER_HOURS}h until it is resolved and the label is removed."
                )
                headline = ":x: *Bad Ticket Flagged*"
            else:
                add_comment(key,
                    f"{BAD_TICKET_FLAG} — Reminder: `bad-ticket` still open after "
                    f"{REMINDER_HOURS}+ hours. Managers tagged again."
                )
                headline = ":warning: *Bad Ticket Reminder*"

            slack_post(
                f"{headline} {rep_tag} {lead_tag} {MEN_LEADERS} — <{url}|{key}>\n"
                f"{summary}\n"
                f"Status: {status}\n"
                f"Please review and correct or close this ticket.",
                CH_OPS,
                ticket_key=key,
            )
            notified += 1

        except Exception as e:
            post_error(f"A9 error on {key}: {e}")

    print(f"[A9] Sent {notified} bad-ticket alert(s)/reminder(s)")


if __name__ == "__main__":
    run()
