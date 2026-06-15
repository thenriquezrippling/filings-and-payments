"""
A3 — Label Quadrant Validator
Polling every 15 min (Mon–Fri). Validates 4 label quadrants on recently updated tickets.

Quadrant rules:
  Workstream (exactly 1):  NoticeQueue_task | new_hire_reporting | taxnoticebugfix | Amendment_task
  Geographic (at least 1): west/south/northeast/midwest/IRS/federal/pr -region
  Ownership (required):    us-taxops-ticket
  Assigned Team (exactly 1): us-amendments | us-tax-filings | e2e-peo | rip-direct | us-nhr

Auto-restoration: if governance labels were stripped by an external automation,
A3 silently re-adds any that appear in the most recent changelog entry and belong
to our known taxonomy — before deciding whether to flag the ticket.

Dedup: AUTO_FLAG:LABEL_QUADRANT prevents re-alerting same ticket.
Label: `missing-labels` added/removed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

WORKSTREAM_LABELS = {
    "NoticeQueue_task", "new_hire_reporting",
    "taxnoticebugfix", "Amendment_task",
}
REGION_LABELS = {
    "west-region", "south-region", "northeast-region",
    "midwest-region", "IRS-region", "federal-region", "pr-region",
}
TEAM_LABELS = {
    "us-amendments", "us-tax-filings",
    "e2e-peo", "rip-direct", "us-nhr",
}
OWNERSHIP_LABEL = "us-taxops-ticket"

# All labels we own and are allowed to auto-restore
ALL_GOVERNANCE_LABELS = WORKSTREAM_LABELS | REGION_LABELS | TEAM_LABELS | {OWNERSHIP_LABEL}


def _validate_quadrants(labels):
    label_set = set(labels)
    issues    = []

    if OWNERSHIP_LABEL not in label_set:
        issues.append(f"Missing ownership label: `{OWNERSHIP_LABEL}`")

    ws_present = label_set & WORKSTREAM_LABELS
    if len(ws_present) == 0:
        issues.append("Missing workstream label — add one of: NoticeQueue_task, new_hire_reporting, taxnoticebugfix, Amendment_task")
    elif len(ws_present) > 1:
        issues.append(f"Multiple workstream labels ({', '.join(sorted(ws_present))}) — exactly 1 required")

    if not (label_set & REGION_LABELS):
        issues.append("Missing geographic region label — add one of: west / south / northeast / midwest / IRS / federal / pr")

    team_present = label_set & TEAM_LABELS
    if len(team_present) == 0:
        issues.append("Missing assigned-team label — add one of: us-amendments, us-tax-filings, e2e-peo, rip-direct, us-nhr")
    elif len(team_present) > 1:
        issues.append(f"Multiple team labels ({', '.join(sorted(team_present))}) — exactly 1 required")

    return issues


def run():
    issues = jira_search(
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} AND {JQL_TAXOPS_OWNED} AND created >= "{GOVERNANCE_START}" AND updated >= "-30m"',
        fields=COMMON_FIELDS,
    )
    print(f"[A3] {len(issues)} recently updated tickets to check")

    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        labels  = get_labels(issue)

        # Always ensure ownership label is present
        if OWNERSHIP_LABEL not in labels:
            try:
                add_label(issue, key, OWNERSHIP_LABEL)
                labels = labels + [OWNERSHIP_LABEL]
                issue["fields"]["labels"] = labels
            except Exception as e:
                post_error(f"A3 could not add ownership label to {key}: {e}")

        try:
            # Before flagging — attempt to silently restore any governance labels
            # that were stripped by an external automation (e.g. another team's Jira rule)
            restored = restore_governance_labels(issue, key, labels, ALL_GOVERNANCE_LABELS)
            if restored:
                labels = get_labels(issue)
                print(f"[A3] {key} — auto-restored stripped labels: {', '.join(sorted(restored))}")

            quad_issues = _validate_quadrants(labels)

            if quad_issues:
                if not has_auto_flag(key, "AUTO_FLAG:LABEL_QUADRANT"):
                    issue_list = "\n".join(f"  • {i}" for i in quad_issues)
                    add_comment(key,
                        f"AUTO_FLAG:LABEL_QUADRANT — Label Quadrant Validation Failed.\n\n"
                        f"{issue_list}\n\n"
                        f"Please correct the labels. See label guide for required values."
                    )
                    add_label(issue, key, "missing-labels")

                    is_peo   = "e2e-peo" in labels
                    rep_tag  = reporter_tag_for(issue)
                    lead_tag = lead_tag_for(labels, is_peo)

                    slack_post(
                        f":label: *Label Quadrant Issue* {rep_tag} {lead_tag} — <{url}|{key}>\n"
                        f"{summary}\n"
                        f"*Missing:*\n" + "\n".join(f"• {i}" for i in quad_issues),
                        CH_LEAD,
                        ticket_key=key,
                    )
            else:
                if "missing-labels" in labels:
                    remove_label(issue, key, "missing-labels")
                    print(f"[A3] {key} labels now valid — removed missing-labels")

        except Exception as e:
            post_error(f"A3 error on {key}: {e}")


if __name__ == "__main__":
    run()
