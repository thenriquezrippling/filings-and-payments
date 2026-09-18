"""
A2 — Quality Gate Checker
Polling every 15 min (Mon–Fri). Validates required fields on recently updated tickets.

Required fields checked:
  - Summary (non-empty)
  - Identity fields in summary and/or description:
      Company ID; PCIH or FFID (at least one); Entity Name or EIN (at least one);
      State; Tax Type
  - Description present and contains issue-detail headers
  - Priority set
  - Assignee set
  - "Reviewed and signed off by:" line present
  - Salesforce Case linked (exempt for filings-amendments-region + Amendment_task or filing workstream)
  - At least one region label
  - At least one valid Tax Platform component (per Confluence routing table)

Component reference: https://rippling.atlassian.net/wiki/spaces/ENG/pages/5508040353

Dedup: AUTO_FLAG:QUALITY_GATE comment prevents re-alerting on the same ticket.
Label: `qa-incomplete` added on failure, removed when all checks pass.
Adds `missing-sfdc-link` when no Salesforce Case is associated via the connector (and no description fallback).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from a3_label_quadrant import validate_label_quadrants
from a4_signoff_mismatch import validate_signoff_text

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

# Description-only checks (identity fields may appear in summary instead)
DESCRIPTION_CHECKS = [
    (r"(Issue|Current\s+Behavior|Expected\s+Behavior)", "Issue / Current Behavior / Expected Behavior"),
]


def _combined_text(issue):
    """Searchable text from summary and description."""
    summary = (issue["fields"].get("summary") or "").strip()
    desc    = desc_text(issue) or ""
    return f"{summary}\n{desc}"


def _validate_identity_fields(text):
    """Validate Company ID, PCIH/FFID, Entity Name/EIN, State, and Tax Type."""
    reasons = []

    if not re.search(r"Company\s+ID", text, re.IGNORECASE):
        reasons.append("Missing required field: Company ID")

    has_pcih = bool(re.search(r"\bPCIH\b", text, re.IGNORECASE))
    has_ffid = bool(re.search(r"\bFFID\b", text, re.IGNORECASE))
    if not has_pcih and not has_ffid:
        reasons.append("Missing required field: PCIH or FFID")

    has_entity = bool(re.search(r"Entity\s+Name", text, re.IGNORECASE))
    has_ein    = bool(re.search(r"\bEIN\b", text, re.IGNORECASE))
    if not has_entity and not has_ein:
        reasons.append("Missing required field: Entity Name or EIN")

    if not re.search(r"\bState\b", text, re.IGNORECASE):
        reasons.append("Missing required field: State")
    if not re.search(r"Tax\s+Type", text, re.IGNORECASE):
        reasons.append("Missing required field: Tax Type")

    return reasons


def _validate_salesforce_case(issue):
    """Require Appfire SF connector Case link; description reference is fallback only."""
    labels = get_labels(issue)
    if is_filings_amendments_sfdc_exempt(labels):
        return []

    key  = issue["key"]
    desc = desc_text(issue) or ""

    if has_salesforce_case_linked(key):
        return []

    if description_has_salesforce_reference(desc):
        return []

    return [
        "No Salesforce Case linked — use Connector for Salesforce (bottom-left panel → "
        "Associate → Case). If association is not possible, add the Salesforce case URL "
        "or Case # to the description."
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

    reasons.extend(_validate_identity_fields(_combined_text(issue)))

    if not desc or len(desc.strip()) < 30:
        reasons.append("Description is empty or too short")
    else:
        for pat, label in DESCRIPTION_CHECKS:
            if not re.search(pat, desc, re.IGNORECASE):
                reasons.append(f"Missing required field: {label}")

        if not re.search(r"Reviewed and signed off by", desc, re.IGNORECASE):
            reasons.append('Missing "Reviewed and signed off by:" line')

    reasons.extend(_validate_salesforce_case(issue))

    if not fields.get("priority"):
        reasons.append("Priority not set")

    if not fields.get("assignee"):
        reasons.append("Assignee not set")

    if not has_geographic_label(labels):
        reasons.append("Missing geographic region label (west / south / northeast / midwest / IRS / federal / pr / filings-amendments-region)")

    # Component validation — must have at least one valid Tax Platform routing component
    if not components:
        reasons.append("No component set — must select a Tax Platform component (Tax Payment, Filing Factory, Amendment, Tax Filing, etc.)")
    elif not any(c in VALID_COMPONENTS for c in components):
        invalid = ", ".join(components)
        reasons.append(f"Component '{invalid}' is not a valid Tax Platform routing component — see routing table")

    return reasons


def _run_legacy():
    issues = jira_search(
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} AND {JQL_TAXOPS_OWNED} AND updated >= "-30m"',
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
            sf_failure = any("Salesforce Case" in f for f in failures)

            if failures:
                if not has_auto_flag(key, "AUTO_FLAG:QUALITY_GATE"):
                    failure_list = "\n".join(f"  • {f}" for f in failures)
                    add_comment(key,
                        f"AUTO_FLAG:QUALITY_GATE — Quality Gate Check Failed.\n\n"
                        f"The following required fields are missing or incomplete:\n{failure_list}\n\n"
                        f"Please complete these fields to clear the `qa-incomplete` label."
                    )
                    add_label(issue, key, "qa-incomplete")
                    if sf_failure:
                        add_label(issue, key, MISSING_SFDC_LINK_LABEL)
                    elif MISSING_SFDC_LINK_LABEL in labels:
                        remove_label(issue, key, MISSING_SFDC_LINK_LABEL)

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
                if MISSING_SFDC_LINK_LABEL in labels:
                    remove_label(issue, key, MISSING_SFDC_LINK_LABEL)
                    print(f"[A2] {key} — removed {MISSING_SFDC_LINK_LABEL}")

        except Exception as e:
            post_error(f"A2 error on {key}: {e}")


def evaluate_shared_quality_gate(issue):
    """Authoritative, side-effect-free shared Quality Gate evaluation."""
    fields = issue.get("fields", {})
    labels = get_labels(issue)
    priority_name = (fields.get("priority") or {}).get("name", "")
    a2_failures = _validate(issue)
    a3_failures = validate_label_quadrants(labels, shared_origin_mode=True)
    a4_failures = validate_signoff_text(issue)
    origin = validate_origin_team_labels(labels)
    reviewer = reviewer_validation_status(issue, origin.get("origin_team", ""))
    routing = routing_config_status(origin.get("origin_team", ""))
    p0 = p0_verification_status(labels)
    priority_plan = priority_label_plan(labels, priority_name, reviewer_validation_verified=reviewer.get("verified", False), p0_verified=p0.get("verified", False))
    blocking = []
    for part in (a2_failures, a3_failures, a4_failures, origin.get("failures", []), priority_plan.get("failures", [])):
        blocking.extend(part)
    for item in (reviewer, routing, p0):
        if item.get("failure"):
            blocking.append(item["failure"])
    return {
        "quality_gate_passed": False if blocking else True,
        "issue_key": issue.get("key", ""),
        "evaluated_updated_at": fields.get("updated", ""),
        "current_status": (fields.get("status") or {}).get("name", ""),
        "origin_team": origin.get("origin_team", ""),
        "jira_priority": priority_name,
        "desired_engineering_priority_label": priority_plan.get("desired", ""),
        "a2_failures": a2_failures,
        "a3_failures": a3_failures,
        "a4_failures": a4_failures,
        "origin_failures": origin.get("failures", []),
        "reviewer_validation_status": reviewer.get("status", "unavailable"),
        "routing_configuration_status": routing.get("status", "missing"),
        "p0_verification_status": p0.get("status", "not_present"),
        "blocking_failures": blocking,
        "warnings": priority_plan.get("warnings", []),
        "can_sync_priority_label": False,
        "can_transition_open": False,
    }

def _run_shared_orchestrated():
    issues = jira_search(f'{BASE_JQL} AND {JQL_OPEN_ONLY} AND updated >= "-30m"', fields=COMMON_FIELDS + ["description", "components"])
    print(f"[A2] shared Quality Gate evaluating {len(issues)} recently updated tickets")
    for issue in issues:
        key = issue["key"]
        try:
            result = evaluate_shared_quality_gate(issue)
            failures = result["blocking_failures"]
            if failures:
                failure_list = "\n".join(f"• {f}" for f in failures)
                print(f"[A2] {key} shared Quality Gate blocked:\n{failure_list}")
                if not has_auto_flag(key, "AUTO_FLAG:SHARED_QUALITY_GATE"):
                    add_comment(key, "AUTO_FLAG:SHARED_QUALITY_GATE — Shared Quality Gate blocked.\n\n" + failure_list + "\n\nNo Engineering priority labels or Jira statuses were changed because reviewer validation is not verifiable.")
            else:
                print(f"[A2] {key} shared Quality Gate checks pass, but automation remains report-only until reviewer validation is configured")
        except Exception as e:
            post_error(f"A2 shared Quality Gate error on {key}: {e}")

def run():
    if shared_quality_gate_enabled():
        return _run_shared_orchestrated()
    return _run_legacy()


if __name__ == "__main__":
    run()
