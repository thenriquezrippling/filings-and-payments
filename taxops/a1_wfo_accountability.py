"""
A1 — Waiting-for-Ops Accountability
Polling every 15 min via GitHub Actions (Mon–Fri only).

Escalation ladder:
  0h  → Initial notification — tags reporter + lead, includes description context
  24h biz → Escalation — tags @us-taxops-leaders + @us-taxops-region-coordinators + reporter
  72h calendar → Hard escalation — tags @taxops-pillar-leads + reporter
  Done → Completion update in thread

Ops response detection:
  When the reporter (TaxOps IC) or assignee comments after entering Waiting for Ops,
  auto-transition to In Progress and clear WFO labels. No time limit — valid through
  the full WFO period (24–48h+). Uses changelog for WFO entry time when available.

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
        f'{BASE_JQL} AND {JQL_TAXOPS_OWNED} AND status = "Waiting for Ops"',
        fields=COMMON_FIELDS + ["description"],
    )
    print(f"[A1] {len(issues)} tickets in Waiting for Ops")

    for issue in issues:
        key           = issue["key"]
        fields        = issue["fields"]
        summary       = fields.get("summary", "(no summary)")
        url           = issue_url(key)
        labels        = get_labels(issue)
        is_peo        = "e2e-peo" in labels
        assignee_name = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        priority      = (fields.get("priority") or {}).get("name", "Unknown")
        entry_ts      = fields.get("statuscategorychangedate", "")

        try:
            _process(issue, key, summary, url, labels, is_peo,
                     assignee_name, priority, entry_ts)
        except Exception as e:
            post_error(f"A1 error on {key}: {e}")

    # Clean up WFO labels from tickets that are Done
    done_issues = jira_search(
        f'{BASE_JQL} AND {JQL_TAXOPS_OWNED} AND status = Done AND labels = "waiting-for-ops"',
        fields=COMMON_FIELDS,
    )
    print(f"[A1] {len(done_issues)} Done tickets with WFO labels to clean up")

    for issue in done_issues:
        key     = issue["key"]
        labels  = get_labels(issue)
        if not any(l.startswith("waiting-for-ops") for l in labels):
            continue
        summary = issue["fields"].get("summary", "(no summary)")
        url     = issue_url(key)
        rep_tag = reporter_tag_for(issue)
        try:
            remove_labels_matching(issue, key, "waiting-for-ops")
            if not has_auto_flag(key, "AUTO_FLAG:DONE_UPDATE"):
                slack_post(
                    f":white_check_mark: *WFO Resolved* {rep_tag} — <{url}|{key}>\n"
                    f"{summary}\nTicket has been marked Done. No further action required.",
                    CH_OPS,
                    ticket_key=key,
                )
        except Exception as e:
            post_error(f"A1 done-cleanup error on {key}: {e}")


def _process(issue, key, summary, url, labels, is_peo,
             assignee_name, priority, entry_ts):
    elapsed_biz_h       = biz_hours_since(entry_ts)
    elapsed_cal_h       = calendar_hours_since(entry_ts)
    rep_tag             = reporter_tag_for(issue)
    lead_tag            = lead_tag_for(labels, is_peo)
    reporter_account_id = (issue["fields"].get("reporter") or {}).get("accountId", "")
    assignee_account_id = (issue["fields"].get("assignee") or {}).get("accountId", "")

    # -- Ops response detection (highest priority check) ----------------------
    # Reporter/assignee comment since entering WFO → move back to In Progress.
    if not has_auto_flag(key, "AUTO_FLAG:OPS_RESPONDED"):
        wfo_since = status_entered_at(key, "Waiting for Ops") or _safe_parse_dt(entry_ts)
        if wfo_since and ops_has_responded(
            key, reporter_account_id, since_dt=wfo_since, assignee_account_id=assignee_account_id
        ):
            transitioned = transition_issue(key, "In Progress")
            if transitioned:
                add_comment(key,
                    "AUTO_FLAG:OPS_RESPONDED — Ops team responded. "
                    "Transitioned to In Progress and cleared WFO queue labels."
                )
                remove_labels_matching(issue, key, "waiting-for-ops")
                slack_post(
                    f":speech_balloon: *WFO Ops Response* {rep_tag} {lead_tag} — <{url}|{key}>\n"
                    f"{summary}\n"
                    f"Ops team has responded. Ticket moved to In Progress and WFO labels cleared.",
                    CH_OPS,
                    ticket_key=key,
                )
            elif not has_auto_flag(key, "AUTO_FLAG:WFO_TRANSITION_FAILED"):
                add_comment(key,
                    "AUTO_FLAG:WFO_TRANSITION_FAILED — Ops responded but In Progress "
                    "transition is unavailable. Please update status manually."
                )
                post_error(
                    f"A1 {key}: Ops responded in WFO but transition to In Progress failed."
                )
            return

    # Pull first 300 chars of description for context
    raw_desc     = desc_text(issue).strip()
    desc_snippet = (raw_desc[:300] + "…") if len(raw_desc) > 300 else raw_desc
    context_line = f"*Issue:* {desc_snippet}" if desc_snippet else ""

    # Level 0 — Initial notification
    if not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_INITIAL"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_INITIAL — Entered Waiting for Ops queue.")
        add_label(issue, key, "waiting-for-ops")

        body = (
            f":hourglass_flowing_sand: *Waiting for Ops* {rep_tag} {lead_tag} — <{url}|{key}>\n"
            f"{summary}\n"
            f"*Priority:* {priority} | *Assignee:* {assignee_name}\n"
        )
        if context_line:
            body += f"{context_line}\n"
        body += "*Action:* Please review this ticket and respond to the requester."

        slack_post(body, CH_OPS, ticket_key=key)

        reporter_name = ((issue["fields"].get("reporter") or {}).get("displayName") or "").lower()
        if reporter_name in SPECIAL_REPORTER_NAMES:
            slack_post(
                f":bell: *FYI* <@{RANA_UID}> <@{TONY_SLACK_UID}> — <{url}|{key}> was submitted by "
                f"{reporter_name.title()} and has entered Waiting for Ops.\n{summary}",
                CH_OPS,
                ticket_key=key,
            )
        return

    # Level 1 — 24 business hours
    if elapsed_biz_h >= 24 and not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_24H"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_24H — 24 business hours elapsed, no response.")
        add_label(issue, key, "waiting-for-ops-24h")
        slack_post(
            f":alarm_clock: *WFO 24h Escalation* {MEN_LEADERS} {REGION_COORDINATORS_MENTION} {rep_tag} — <{url}|{key}>\n"
            f"{summary}\n"
            f"*Priority:* {priority} | *Assignee:* {assignee_name}\n"
            f"*Issue:* No response after 24 business hours.\n"
            f"*Action:* Region leads — please intervene and ensure this ticket is actioned immediately.",
            CH_OPS,
            ticket_key=key,
        )
        return

    # Level 2 — 72 calendar hours
    if elapsed_cal_h >= 72 and not has_auto_flag(key, "AUTO_FLAG:WAITING_OPS_72H"):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_72H — 72 calendar hours elapsed.")
        add_label(issue, key, "waiting-for-ops-72h")
        slack_post(
            f":rotating_light: *WFO 72h HARD ESCALATION* {MEN_LEADS2} {rep_tag} — <{url}|{key}>\n"
            f"{summary}\n"
            f"*Priority:* {priority} | *Assignee:* {assignee_name}\n"
            f"*Issue:* 72 hours elapsed with no response — customer is waiting.\n"
            f"*Action:* Immediate response required. Escalate to leadership if blocked.",
            CH_OPS,
            ticket_key=key,
        )


if __name__ == "__main__":
    run()
