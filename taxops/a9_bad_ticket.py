"""
A9 - Bad Ticket Notifier
Polling every 15 min.

Watches for tickets with the `bad-ticket` label.
When found (and not yet notified), posts to CH_OPS tagging:
  - Reporter display name
  - @us-taxops-leaders

Dedup: AUTO_FLAG:BAD_TICKET comment on the Jira issue.
Re-sweeps all open bad-ticket issues on every run (catch-up for downtime).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *


def run():
    issues = jira_search(
        f'{BASE_JQL} AND labels = "bad-ticket"',
        fields=COMMON_FIELDS,
    )
    print(f"[A9] {len(issues)} tickets with bad-ticket label")

    notified = 0
    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        status  = (fields.get("status") or {}).get("name", "Unknown")
        reporter_name = (fields.get("reporter") or {}).get("displayName", "Unknown Reporter")

        try:
            if has_auto_flag(key, "AUTO_FLAG:BAD_TICKET"):
                continue

            add_comment(key,
                f"AUTO_FLAG:BAD_TICKET — Bad Ticket notification sent.\n"
                f"This ticket has been flagged with the `bad-ticket` label "
                f"and a notification has been posted to #taxops_case_help."
            )

            slack_post(
                f":x: *Bad Ticket Flagged* {MEN_LEADERS} — <{url}|{key}>\n"
                f"{summary}\n"
                f"Status: {status} | Reporter: {reporter_name}\n"
                f"Please review and correct or close this ticket.",
                CH_OPS,
                ticket_key=key,
            )
            notified += 1

        except Exception as e:
            post_error(f"A9 error on {key}: {e}")

    print(f"[A9] Notified on {notified} new bad tickets")


if __name__ == "__main__":
    run()
