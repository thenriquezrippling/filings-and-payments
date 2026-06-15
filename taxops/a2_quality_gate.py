"""
A2 — Quality Gate Checker
Polling every 15 min (Mon–Fri). Validates required fields on recently updated tickets.

Required fields checked:
  - Summary (non-empty)
  - Description present and contains key field headers
  - Priority set
  - Assignee set
  - "Reviewed and signed off by:" line present
  - Salesforce case reference
  - At least one region label
  - At least one valid Tax Platform component (per Confluence routing table)

Component reference: https://rippling.atlassian.net/wiki/spaces/ENG/pages/5508040353

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

# Valid components from Tax Platform Support tickets routing table
# Source: https://rippling.atlassian.net/wiki/spaces/ENG/pages/5508040353
VALID_COMPONENTS = {
    # Tax Payments
    "Tax Payment", "Tax Adjustment", "Tax Draft", "Tax Refund",
    # FF Platform
    "Filing Factory (FF)", "New Hire Reporting",
    # EE Filings
    "W2", "W2C", "1099", "1099c",
    # Amendments
    "Amendments Data", "Amendment",
    # ER Filings
    "Tax Filing", "CFS and EFS", "Filing Code", "QE Adjustment",
    "QE Processing", "QE Reconciliation Run", "Quarter End Packages",
    # Tax Calculation
    "Tax Calculations", "tax-calculation", "Tax Explanation",
    # Tax Exchange
    "Tax Exchange", "Legal Name Change", "Mapping issues",
    "R&D Credit Migration April '26",
    # Tax R&D Support
    "Non-Eng Support Ticket",
}

# (regex_pattern, human_readable_label)
REQUIRED_CHECKS = [
    (r"Company\s+ID",                                   "Company ID"),
    (r"(PCIH\s+ID|FFID|Entity\s+Name|EIN)",             "PCIH ID / FFID / Entity Name / EIN"),
    (r"(State|Tax\s+Type)",                             "State / Tax Type"),
    (r"(Issue|Current\s+Behavior|Expected\s+Behavior)", "Issue / Current Behavior / Expected Behavior"),
]


def _validate(issue):
    """Return list of failure reasons. Empty list = pass."""
    fields     = issue["fields"]
    summary    = (fields.get("summary") or "").strip()
    desc       = desc_text(issue)
    labels     = get_labels(issue)
    components = [c.get("name", "") for c in (fields.get("components") or [])]
    reasons    = []

    if not summary:
        reasons.append("Missing summary")

    if not desc or len(desc.strip()) < 30:
        reasons.append("Description is empty or too short")
    else:
        for pat, label in REQUIRED_CHECKS:
            if not re.search(pat, desc, re.IGNORECASE):
                reasons.append(f"Missing required field: {label}")

        if not re.search(r"Reviewed and signed off by", desc, re.IGNORECASE):
            reasons.append('Missing "Reviewed and signed off by:" line')

        sf_pattern = r"(salesforce\.com|Case\s*#\s*\d+|SF-\d+)"
        if not re.search(sf_pattern, desc, re.IGNORECASE):
            reasons.append("Missing Salesforce case link or Case # reference")

    if not fields.get("priority"):
        reasons.append("Priority not set")

    if not fields.get("assignee"):
        reasons.append("Assignee not set")

    if not any(l in REGION_LABELS for l in labels):
        reasons.append("Missing geographic region label (west / south / northeast / midwest / IRS / federal / pr)")

    # Component validation — must have at least one valid Tax Platform routing component
    if not components:
        reasons.append("No component set — must select a Tax Platform component (Tax Payment, Filing Factory, Amendment, Tax Filing, etc.)")
    elif not any(c in VALID_COMPONENTS for c in components):
        invalid = ", ".join(components)
        reasons.append(f"Component '{invalid}' is not a valid Tax Platform routing component — see routing table")

    return reasons


def run():
    issues = jira_search(
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} AND {JQL_TAXOPS_OWNED} AND created >= "{GOVERNANCE_START}" AND updated >= "-30m"',
        fields=COMMON_FIELDS + ["description", "components"],
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
                if not has_auto_flag(key, "AUTO_FLAG:QUALITY_GATE"):
                    failure_list = "\n".join(f"  • {f}" for f in failures)
                    add_comment(key,
                        f"AUTO_FLAG:QUALITY_GATE — Quality Gate Check Failed.\n\n"
                        f"The following required fields are missing or incomplete:\n{failure_list}\n\n"
                        f"Please complete these fields to clear the `qa-incomplete` label."
                    )
                    add_label(issue, key, "qa-incomplete")

                    is_peo   = "e2e-peo" in labels
                    rep_tag  = reporter_tag_for(issue)
                    lead_tag = lead_tag_for(labels, is_peo)

                    slack_post(
                        f":x: *Quality Gate Failed* {rep_tag} {lead_tag} — <{url}|{key}>\n"
                        f"{summary}\n"
                        f"*Missing:*\n" + "\n".join(f"• {f}" for f in failures),
                        CH_LEAD,
                        ticket_key=key,
                    )
            else:
                if "qa-incomplete" in labels:
                    remove_label(issue, key, "qa-incomplete")
                    print(f"[A2] {key} now passes QG — removed qa-incomplete")

        except Exception as e:
            post_error(f"A2 error on {key}: {e}")


if __name__ == "__main__":
    run()
