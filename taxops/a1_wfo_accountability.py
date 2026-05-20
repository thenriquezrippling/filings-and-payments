"""
A1 — Waiting-for-Ops Accountability
Polling every 15 min via GitHub Actions.

Escalation ladder:
  0h  → Initial notification to CH_OPS
  24h biz → Escalate + tag @us-taxops-leaders
  72h calendar → Hard escalation + tag secondary leader group
  Done → Completion update + clean WFO labels

Dedup via AUTO_FLAG comments on each Jira issue (survives restarts).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *


def run():
    # ── 1. Active WFO tickets ────────────────────────────────────────────────
    issues = jira_search(
        f'{BASE_JQL} AND status = "Waiting for Ops"',
        fields=COMMON_FIELDS,
    )
    print(f"[A1] {len(issues)} tickets in Waiting for Ops")

    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        labels  = get_labels(issue)
        is_peo  = "e2e-peo" in labels
        assignee_name = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        entry_ts = fields.get("statuscategorychangedate", "")

        try:
            _process(issue, key, summary, url, labels, is_peo,
                     assignee_name, entry_ts)
        except Exception as e:
            post_error(f"A1 error on {key}: {e}")

    # ── 2. Done tickets still carrying WFO labels ────────────────────────────
    done_issues = jira_search(
        f'{BASE_JQL} AND status = Done AND labels = "waiting-for-ops"',
        fields=COMMON_FIELDS,
    )
    print(f"[A1] {len(done_issues)} Done tickets with WFO labels to clean up")

    for issue in done_issues:
        key     = issue["key"]
        summary = issue["fields"].get("summary", "(no summary)")
        url     = issue_url(key)
        try:
            if not has_auto_flag(key, "AUTO_FLAG:DONE_UPDATE"):
                add_comment(key, "AUTO_FLAG:DONE_UPDATE — Ticket resolved. WFO queue exit recorded.")
                slack_post(
                    f":white_check_mark: *WFO Resolved* — <{url}|{key}>\n"
                    f"{summary}\nTicket has been marked Done.",
                    CH_OPS,
                )
                remove_labels_matching(issue, key, "waiting-for-ops")
        except Exception as e:
            post_error(f"A1 done-cleanup error on {key}: {e}")


def _process(issue, key, summary, url, labels, is_peo,
             assignee_name, entry_ts):
    elapsed_biz_h   = biz_hours_since(entry_ts)
    elapsed_cal_h   = calendar_hours_since(entry_ts)

    # Level 0: Initial notification
    if not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_INITIAL"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_INITIAL — Entered Waiting for Ops queue.")
        add_label(issue, key, "waiting-for-ops")
        slack_post(
            f":hourglass_flowing_sand: *Waiting for Ops* — <{url}|{key}>\n"
            f"{summary}\nAssignee: {assignee_name} | Ops team: please respond.",
            CH_OPS,
        )
        return

    # Level 1: 24 business hours
    if elapsed_biz_h >= 24 and not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_24H"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_24H — 24 business hours elapsed, no response.")
        add_label(issue, key, "waiting-for-ops-24h")
        slack_post(
            f":alarm_clock: *WFO 24h Escalation* {MEN_LEADERS} — <{url}|{key}>\n"
            f"{summary}\nNo response after 24 business hours. Assignee: {assignee_name}.",
            CH_OPS,
        )
        return

    # Level 2: 72 calendar hours
    if elapsed_cal_h >= 72 and not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_72H"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_72H — 72 calendar hours elapsed.")
        add_label(issue, key, "waiting-for-ops-72h")
        slack_post(
            f":rotating_light: *WFO 72h HARD ESCALATION* {MEN_LEADS2} — <{url}|{key}>\n"
            f"{summary}\n72 hours with no response. Assignee: {assignee_name}. "
            f"Immediate attention required.",
            CH_OPS,
        )


if __name__ == "__main__":
    run()
