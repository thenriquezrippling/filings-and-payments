"""
A1 — Waiting-for-Ops Accountability
Polling every 15 min via GitHub Actions (Mon–Fri only).

Escalation ladder:
  0h  → Initial notification — tags reporter + lead
  24h biz → Escalation — tags @us-taxops-leaders + reporter
  72h calendar → Hard escalation — tags @taxops-pillar-leads + reporter
  Done → Completion update in thread

Special rule: tickets reported by Vijay Kumar or Rashmita Topakulu
trigger an immediate FYI alert to Rana and Tony when they enter WFO.

Dedup via AUTO_FLAG comments on each Jira issue (survives restarts).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SPECIAL_REPORTER_NAMES = {"vijay kumar", "rashmita topakulu"}
TONY_SLACK_UID = "U026LRKHS1F"


def run():
    issues = jira_search(
        f'{BASE_JQL} AND status = "Waiting for Ops"',
        fields=COMMON_FIELDS,
    )
    print(f"[A1] {len(issues)} tickets in Waiting for Ops")

    for issue in issues:
        key          = issue["key"]
        fields       = issue["fields"]
        summary      = fields.get("summary", "(no summary)")
        url          = issue_url(key)
        labels       = get_labels(issue)
        is_peo       = "e2e-peo" in labels
        assignee_name = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        entry_ts     = fields.get("statuscategorychangedate", "")

        try:
            _process(issue, key, summary, url, labels, is_peo, assignee_name, entry_ts)
        except Exception as e:
            post_error(f"A1 error on {key}: {e}")

    done_issues = jira_search(
        f'{BASE_JQL} AND status = Done AND labels = "waiting-for-ops"',
        fields=COMMON_FIELDS,
    )
    print(f"[A1] {len(done_issues)} Done tickets with WFO labels to clean up")

    for issue in done_issues:
        key     = issue["key"]
        summary = issue["fields"].get("summary", "(no summary)")
        url     = issue_url(key)
        rep_tag = reporter_tag_for(issue)
        try:
            if not has_auto_flag(key, "AUTO_FLAG:DONE_UPDATE"):
                add_comment(key, "AUTO_FLAG:DONE_UPDATE — Ticket resolved. WFO queue exit recorded.")
                slack_post(
                    f":white_check_mark: *WFO Resolved* {rep_tag} — <{url}|{key}>\n"
                    f"{summary}\nTicket has been marked Done.",
                    CH_OPS,
                    ticket_key=key,
                )
                remove_labels_matching(issue, key, "waiting-for-ops")
        except Exception as e:
            post_error(f"A1 done-cleanup error on {key}: {e}")


def _process(issue, key, summary, url, labels, is_peo, assignee_name, entry_ts):
    elapsed_biz_h = biz_hours_since(entry_ts)
    elapsed_cal_h = calendar_hours_since(entry_ts)
    rep_tag       = reporter_tag_for(issue)
    lead_tag      = lead_tag_for(labels, is_peo)

    if not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_INITIAL"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_INITIAL — Entered Waiting for Ops queue.")
        add_label(issue, key, "waiting-for-ops")
        slack_post(
            f":hourglass_flowing_sand: *Waiting for Ops* {rep_tag} {lead_tag} — <{url}|{key}>\n"
            f"{summary}\nAssignee: {assignee_name} | Ops team: please respond.",
            CH_OPS,
            ticket_key=key,
        )
        reporter_name = ((issue["fields"].get("reporter") or {}).get("displayName") or "").lower()
        if reporter_name in SPECIAL_REPORTER_NAMES:
            slack_post(
                f":bell: *FYI* <@{RANA_UID}> <@{TONY_SLACK_UID}> — <{url}|{key}> was submitted by "
                f"{reporter_name.title()} and has entered Waiting for Ops.\n{summary}",
                CH_OPS,
                ticket_key=key,
            )
        return

    if elapsed_biz_h >= 24 and not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_24H"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_24H — 24 business hours elapsed, no response.")
        add_label(issue, key, "waiting-for-ops-24h")
        slack_post(
            f":alarm_clock: *WFO 24h Escalation* {MEN_LEADERS} {rep_tag} — <{url}|{key}>\n"
            f"{summary}\nNo response after 24 business hours. Assignee: {assignee_name}.",
            CH_OPS,
            ticket_key=key,
        )
        return

    if elapsed_cal_h >= 72 and not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_72H"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_72H — 72 calendar hours elapsed.")
        add_label(issue, key, "waiting-for-ops-72h")
        slack_post(
            f":rotating_light: *WFO 72h HARD ESCALATION* {MEN_LEADS2} {rep_tag} — <{url}|{key}>\n"
            f"{summary}\n72 hours with no response. Assignee: {assignee_name}. "
            f"Immediate attention required.",
            CH_OPS,
            ticket_key=key,
        )


if __name__ == "__main__":
    run()
