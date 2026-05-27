"""
A3 — Label Quadrant Validator
Polling every 15 min. Validates 4 label quadrants on recently updated tickets.

Quadrant rules:
  Workstream (exactly 1):  NoticeQueue_task | new_hire_reporting | taxnoticebugfix | Amendment_task
  Geographic (at least 1): west/south/northeast/midwest/IRS/federal/pr -region
  Ownership (required):    us-taxops-ticket
  Assigned Team (exactly 1): us-amendments | us-tax-filings | e2e-peo | rip-direct | us-nhr

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


def _validate_quadrants(labels):
    label_set = set(labels)
    issues    = []

    # Ownership (always auto-fixed by A8, but flag here too)
    if OWNERSHIP_LABEL not in label_set:
        issues.append(f"Missing ownership label: `{OWNERSHIP_LABEL}`")

    # Workstream: exactly 1
    ws_present = label_set & WORKSTREAM_LABELS
    if len(ws_present) == 0:
        issues.append("Missing workstream label (one of: NoticeQueue_task, new_hire_reporting, taxnoticebugfix, Amendment_task)")
    elif len(ws_present) > 1:
        issues.append(f"Multiple workstream labels found ({', '.join(sorted(ws_present))}) — exactly 1 required")

    # Geographic: at least 1
    if not (label_set & REGION_LABELS):
        issues.append("Missing geographic region label (west/south/northeast/midwest/IRS/federal/pr)")

    # Assigned Team: exactly 1
    team_present = label_set & TEAM_LABELS
    if len(team_present) == 0:
        issues.append("Missing assigned-team label (one of: us-amendments, us-tax-filings, e2e-peo, rip-direct, us-nhr)")
    elif len(team_present) > 1:
        issues.append(f"Multiple team labels found ({', '.join(sorted(team_present))}) — exactly 1 required")

    return issues


def run():
    issues = jira_search(
        f'{BASE_JQL} AND statusCategory != Done AND created >= "{GOVERNANCE_START}" AND updated >= "-30m"',
        fields=COMMON_FIELDS,
    )
    print(f"[A3] {len(issues)} recently updated tickets to check")

    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        labels  = get_labels(issue)

        # Silently ensure us-taxops-ticket is present (A8 does this too)
        if OWNERSHIP_LABEL not in labels:
            try:
                add_label(issue, key, OWNERSHIP_LABEL)
                labels = labels + [OWNERSHIP_LABEL]   # update local copy
                issue["fields"]["labels"] = labels
            except Exception as e:
                post_error(f"A3 could not add ownership label to {key}: {e}")

        try:
            quad_issues = _validate_quadrants(labels)

            if quad_issues:
                if not has_auto_flag(key, "AUTO_FLAG:LABEL_QUADRANT"):
                    issue_list   = "\n".join(f"  • {i}" for i in quad_issues)
                    comment_text = (
                        f"AUTO_FLAG:LABEL_QUADRANT — Label Quadrant Validation Failed.\n\n"
                        f"{issue_list}\n\n"
                        f"Please correct the labels. See label guide for required values."
                    )
                    add_comment(key, comment_text)
                    add_label(issue, key, "missing-labels")

                    is_peo   = "e2e-peo" in labels
                    lead_uid = region_lead_uid(labels, is_peo)
                    lead_tag = f"<@{lead_uid}> " if lead_uid else ""

                    slack_post(
                        f":label: *Label Quadrant Issue* {lead_tag}— <{url}|{key}>\n"
                        f"{summary}\n"
                        f"{'; '.join(quad_issues)}",
                        CH_LEAD,
                        ticket_key=key,
                    )
            else:
                # All quadrants valid — remove missing-labels if present
                if "missing-labels" in labels:
                    remove_label(issue, key, "missing-labels")
                    print(f"[A3] {key} labels now valid — removed missing-labels")

        except Exception as e:
            post_error(f"A3 error on {key}: {e}")


if __name__ == "__main__":
    run()
