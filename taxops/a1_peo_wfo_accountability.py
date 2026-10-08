"""
A1 PEO — Waiting-for-Ops Accountability
Polling every 15 min via GitHub Actions (Mon–Fri only).

Escalation ladder:
  0h  → Initial notification — posts to the PEO Ops channel and best-effort tags reporter
  24h biz → Escalation — posts to the PEO Ops channel and best-effort tags reporter
  72h calendar → Hard escalation — posts to the PEO Ops channel and best-effort tags reporter
  Done → Completion update in thread

Ops response detection:
  Scans reporter comments since entering Waiting for Ops. Because this repo does
  not maintain a PEO Ops Slack/Jira roster, the PEO path treats a substantive
  reporter-authored Jira comment as the response that stops WFO escalations.

  When an actionable ENG-facing response is found:
    - AUTO_FLAG:OPS_RESPONDED is recorded (stops WFO escalations)
    - Ticket is moved to In Progress and WFO labels cleared when transition succeeds


Dedup via AUTO_FLAG comments on each Jira issue (survives restarts).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

def run():
    issues = jira_search(
        f'{BASE_JQL} AND {JQL_PEO_OPS_OWNED} AND status = "Waiting for Ops"',
        fields=COMMON_FIELDS + ["description"],
    )
    print(f"[A1-PEO] {len(issues)} tickets in Waiting for Ops")

    for issue in issues:
        key           = issue["key"]
        fields        = issue["fields"]
        summary       = fields.get("summary", "(no summary)")
        url           = issue_url(key)
        labels        = get_labels(issue)
        assignee_name = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        priority      = (fields.get("priority") or {}).get("name", "Unknown")
        entry_ts      = fields.get("statuscategorychangedate", "")

        try:
            _process(issue, key, summary, url, labels,
                     assignee_name, priority, entry_ts)
        except Exception as e:
            post_error(f"A1 PEO error on {key}: {e}")

    # Clean up WFO labels from tickets that are Done
    done_issues = jira_search(
        f'{BASE_JQL} AND {JQL_PEO_OPS_OWNED} AND status = Done AND labels = "waiting-for-ops"',
        fields=COMMON_FIELDS,
    )
    print(f"[A1-PEO] {len(done_issues)} Done tickets with WFO labels to clean up")

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
                    f":white_check_mark: *PEO WFO Resolved* {rep_tag} — <{url}|{key}>\n"
                    f"{summary}\nTicket has been marked Done. No further action required.",
                    CH_PEO_OPS,
                    ticket_key=key,
                )
        except Exception as e:
            post_error(f"A1 PEO done-cleanup error on {key}: {e}")


def _process(issue, key, summary, url, labels,
             assignee_name, priority, entry_ts):
    rep_tag             = reporter_tag_for(issue, fallback="reporter")
    reporter_account_id = (issue["fields"].get("reporter") or {}).get("accountId", "")

    # Scope all WFO markers to the current Waiting for Ops cycle. A ticket can
    # legitimately leave Waiting for Ops after Ops responds, then re-enter WFO
    # after Engineering replies. In that new cycle, 24h / 72h timers restart.
    wfo_since           = status_entered_at(key, "Waiting for Ops") or _safe_parse_dt(entry_ts)
    wfo_since_str       = wfo_since.isoformat() if wfo_since else entry_ts
    elapsed_biz_h       = biz_hours_since(wfo_since_str)
    elapsed_cal_h       = calendar_hours_since(wfo_since_str)

    if has_auto_flag_since(key, "AUTO_FLAG:OPS_RESPONDED", wfo_since):
        return

    # -- Ops response detection (highest priority check) ----------------------
    response  = find_actionable_wfo_response_from_reporter(key, wfo_since, reporter_account_id) if wfo_since else None

    if response:
        author = response["author"]
        add_comment(key,
            f"AUTO_FLAG:OPS_RESPONDED — Actionable Ops response from {author}. "
            f"Engineering WFO request addressed."
        )
        transitioned = transition_issue(key, "In Progress")
        if transitioned:
            remove_labels_matching(issue, key, "waiting-for-ops")
            status_note = "Ticket moved to In Progress and WFO labels cleared."
        elif not has_auto_flag(key, "AUTO_FLAG:WFO_TRANSITION_FAILED"):
            add_comment(key,
                "AUTO_FLAG:WFO_TRANSITION_FAILED — Ops provided an actionable response "
                "but In Progress transition is unavailable. Please update status manually."
            )
            post_error(f"A1 PEO {key}: actionable Ops response but In Progress transition failed.")
            status_note = "Please move to In Progress manually — transition was unavailable."
        else:
            status_note = "Please move to In Progress manually — transition was unavailable."

        slack_post(
            f":speech_balloon: *PEO WFO Ops Response* {rep_tag} — <{url}|{key}>\n"
            f"{summary}\n"
            f"*{author}* provided an actionable response for Engineering. {status_note}",
            CH_PEO_OPS,
            ticket_key=key,
        )
        return

    # Pull first 300 chars of description for context
    raw_desc     = desc_text(issue).strip()
    desc_snippet = (raw_desc[:300] + "…") if len(raw_desc) > 300 else raw_desc
    context_line = f"*Issue:* {desc_snippet}" if desc_snippet else ""

    # Level 0 — Initial notification
    if not has_auto_flag_since(key, "AUTO_FLAG:WAITING_OPS_INITIAL", wfo_since):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_INITIAL — Entered Waiting for Ops queue.")
        add_label(issue, key, "waiting-for-ops")

        body = (
            f":hourglass_flowing_sand: *PEO Waiting for Ops* {rep_tag} — <{url}|{key}>\n"
            f"{summary}\n"
            f"*Priority:* {priority} | *Assignee:* {assignee_name}\n"
        )
        if context_line:
            body += f"{context_line}\n"
        body += "*Action:* Please review this ticket and respond to the requester."

        slack_post(body, CH_PEO_OPS, ticket_key=key)

        return

    # Level 2 — 72 calendar hours
    if elapsed_cal_h >= 72 and not has_auto_flag_since(key, "AUTO_FLAG:WAITING_OPS_72H", wfo_since):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_72H — 72 calendar hours elapsed.")
        add_label(issue, key, "waiting-for-ops-72h")
        slack_post(
            f":rotating_light: *PEO WFO 72h HARD ESCALATION* {rep_tag} — <{url}|{key}>\n"
            f"{summary}\n"
            f"*Priority:* {priority} | *Assignee:* {assignee_name}\n"
            f"*Issue:* 72 hours elapsed with no response — customer is waiting.\n"
            f"*Action:* Immediate response required. Escalate to leadership if blocked.",
            CH_PEO_OPS,
            ticket_key=key,
        )

    # Level 1 — 24 business hours
    if (
        elapsed_biz_h >= 24
        and not has_auto_flag_since(key, "AUTO_FLAG:WAITING_OPS_24H", wfo_since)
        and not has_auto_flag_since(key, "AUTO_FLAG:WAITING_OPS_72H", wfo_since)
    ):
        add_comment(key, "AUTO_FLAG:WAITING_OPS_24H — 24 business hours elapsed, no response.")
        add_label(issue, key, "waiting-for-ops-24h")
        slack_post(
            f":alarm_clock: *PEO WFO 24h Escalation* {rep_tag} — <{url}|{key}>\n"
            f"{summary}\n"
            f"*Priority:* {priority} | *Assignee:* {assignee_name}\n"
            f"*Issue:* No response after 24 business hours.\n"
            f"*Action:* Please ensure this PEO Ops ticket is actioned immediately.",
            CH_PEO_OPS,
            ticket_key=key,
        )
        return



if __name__ == "__main__":
    run()
