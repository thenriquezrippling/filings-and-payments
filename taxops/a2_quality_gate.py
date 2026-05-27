"""
A2 — Quality Gate Checker
Polling every 15 min. Validates required fields in recently created/updated tickets.

Required fields checked:
  - Summary (non-empty)
  - Description present and contains key field headers
  - Priority set
  - Assignee set
  - "Reviewed and signed off by:" line present
  - Salesforce case reference (salesforce.com URL or "Case #" pattern)
  - At least one region label

Dedup: AUTO_FLAG:QUALITY_GATE comment prevents re-alerting on the same ticket.
Label: `qa-incomplete` added on failure, removed when all checks pass.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

REGION_LABELS = {
    "west-region", "south-region", "northeast-region",
    "midwest-region", "IRS-region", "federal-region", "pr-region",
}

# Key phrases that must appear in the description
REQUIRED_PATTERNS = [
    r"Company\s+ID",
    r"(PCIH\s+ID|FFID|Entity\s+Name|EIN)",
    r"(State|Tax\s+Type)",
    r"(Issue|Current\s+Behavior|Expected\s+Behavior)",
]


def _validate(issue):
    """Return list of failure reasons. Empty list = pass."""
    fields  = issue["fields"]
    summary = (fields.get("summary") or "").strip()
    desc    = desc_text(issue)
    labels  = get_labels(issue)
    reasons = []

    if not summary:
        reasons.append("Missing summary")

    if not desc or len(desc.strip()) < 30:
        reasons.append("Description empty or too short")
    else:
        for pat in REQUIRED_PATTERNS:
            if not re.search(pat, desc, re.IGNORECASE):
                reasons.append(f"Description missing: `{pat}`")

        if not re.search(r"Reviewed and signed off by", desc, re.IGNORECASE):
            reasons.append("Missing \"Reviewed and signed off by:\" line")

        sf_pattern = r"(salesforce\.com|Case\s*#\s*\d+|SF-\d+)"
        if not re.search(sf_pattern, desc, re.IGNORECASE):
            reasons.append("No Salesforce case link or reference found")

    if not fields.get("priority"):
        reasons.append("Priority not set")

    if not fields.get("assignee"):
        reasons.append("Assignee not set")

    if not any(l in REGION_LABELS for l in labels):
        reasons.append("No geographic region label (west/south/northeast/midwest/IRS/federal/pr)")

    return reasons


def run():
    issues = jira_search(
        f'{BASE_JQL} AND statusCategory != Done AND created >= "{GOVERNANCE_START}" AND updated >= "-30m"',
        fields=COMMON_FIELDS + ["description"],
    )
    print(f"[A2] {len(issues)} recently updated tickets to validate")

    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        labels  = get_labels(issue)

        try:
            failures = _validate(issue)

            if failures:
                # Only alert if we haven't already flagged this ticket
                if not has_auto_flag(key, "AUTO_FLAG:QUALITY_GATE"):
                    failure_list = "\n".join(f"  • {f}" for f in failures)
                    comment_text = (
                        f"AUTO_FLAG:QUALITY_GATE — Quality Gate Check Failed.\n\n"
                        f"The following required fields are missing or incomplete:\n{failure_list}\n\n"
                        f"Please complete these fields to clear the `qa-incomplete` label."
                    )
                    add_comment(key, comment_text)
                    add_label(issue, key, "qa-incomplete")

                    # Find lead to notify
                    is_peo    = "e2e-peo" in labels
                    lead_uid  = region_lead_uid(labels, is_peo)
                    channel   = CH_LEAD if lead_uid else CH_OPS
                    lead_tag  = f"<@{lead_uid}> " if lead_uid else ""

                    slack_post(
                        f":x: *Quality Gate Failed* {lead_tag}— <{url}|{key}>\n"
                        f"{summary}\n"
                        f"Missing: {', '.join(failures)}",
                        channel,
                        ticket_key=key,
                    )
            else:
                # Ticket now passes — remove qa-incomplete label if present
                if "qa-incomplete" in labels:
                    remove_label(issue, key, "qa-incomplete")
                    print(f"[A2] {key} now passes QG — removed qa-incomplete")

        except Exception as e:
            post_error(f"A2 error on {key}: {e}")


if __name__ == "__main__":
    run()
