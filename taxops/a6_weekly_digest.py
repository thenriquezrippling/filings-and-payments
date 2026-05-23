"""
A6 — Weekly Executive QA Digest
Runs every Monday at 12:00 PM ET (16:00 UTC).

Posts to CH_EXEC (#taxops-leadership) via Zapier webhook:
  headline: short narrative executive summary (top-level post)
  detail:   full breakdown per WBR spec (thread reply)

Every count includes hyperlinked ticket examples:
  ≤5 tickets  → list individual <URL|KEY> links
  >5 tickets  → link to Jira filter URL

WoW comparison stored in taxops/wbr_history.json.
Governance metrics only cover tickets created >= GOVERNANCE_START.
SLA and volume metrics cover ALL open tickets.
"""
import sys, os, json, re, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from datetime import datetime
from collections import Counter
import requests as _req

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "wbr_history.json")

TAX_TYPES = ["SUI", "FML", "FUTA", "SUTA", "941", "940", "W-2", "1099",
             "SDI", "SIT", "FIT", "FICA", "local"]
TAX_RE = re.compile(r'\b(' + '|'.join(re.escape(t) for t in TAX_TYPES) + r')\b', re.IGNORECASE)

STOPWORDS = {
    "the","a","an","and","or","for","in","on","at","to","of","is","are",
    "was","were","with","this","that","from","by","not","be","it","as",
    "we","i","s","re","has","have","had","will","can","do","did","does",
    "its","but","so","if","into","than","no","he","she","they","them",
    "our","you","your","all","new","per","get","via","need","also",
    "issue","ticket","please","update","pcih","inc","llc","corp",
    "unable","upload","result","file","help","know","here","what",
    "when","where","which","then","just","been","have","more","also",
    "some","such","only","other","than","very","well","back",
}

NOISE = {"psd", "pjr", "pcih", "ffid", "noticequeue", "task"}

OPEN_STATUSES_EXCLUDE = ("Done", "Closed", "Resolved")

BASE_OPEN_FILTER_JQL = (
    'project = PF AND issuetype = "Ops - Customer Task" '
    'AND labels = "us-taxops-ticket" '
    'AND status not in (Done, Closed, Resolved)'
)
GOV_OPEN_FILTER_JQL = (
    BASE_OPEN_FILTER_JQL
    + f' AND created >= "{GOVERNANCE_START}"'
)

CC_REGION_LEADS = "<@U031NBG0E82> <@U026W3ACSU8>"
CC_ENG_TAXOPS   = "<@U026W3CCKLG> <@U026LRKHS1F>"
CC_MANAGERS     = "<!subteam^S06URQSJGEN>"
CC_PRODUCT_ENG  = "<@U026LRKHS1F> <@U026W3CCKLG> <@U01F7MRSW5V>"
CC_LEADERSHIP   = "<!subteam^S0ANS8X2B7Y>"


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def wow(current, prev):
    if prev is None:
        return str(current)
    diff = current - prev
    if diff > 0:
        return f"{current} (↑{diff} WoW)"
    elif diff < 0:
        return f"{current} (↓{abs(diff)} WoW)"
    return f"{current} (no change WoW)"


# ---------------------------------------------------------------------------
# Link formatting helpers
# ---------------------------------------------------------------------------

def jira_filter_url(jql):
    return "https://rippling.atlassian.net/issues/?jql=" + urllib.parse.quote(jql + " ORDER BY created ASC")


def fmt_links(issues, jql_for_filter, limit=5):
    if not issues:
        return "none"
    if len(issues) <= limit:
        return " ".join(f"<{issue_url(i['key'])}|{i['key']}>" for i in issues)
    url = jira_filter_url(jql_for_filter)
    return f"<{url}|View all {len(issues)} tickets ↗>"


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------

def top_tax_types_with_issues(issues_list, n=5):
    buckets: dict = {}
    for issue in issues_list:
        summary = issue["fields"].get("summary", "")
        seen = set()
        for m in TAX_RE.findall(summary):
            key = m.upper()
            if key not in seen:
                buckets.setdefault(key, []).append(issue)
                seen.add(key)
    return sorted(buckets.items(), key=lambda x: -len(x[1]))[:n]


def top_bigrams_with_issues(issues_list, n=5, min_count=2):
    phrase_map: dict = {}
    for issue in issues_list:
        summary = issue["fields"].get("summary", "")
        words = [w for w in re.findall(r'\b[a-z]{4,}\b', summary.lower())
                 if w not in STOPWORDS and w not in NOISE]
        seen_in_this = set()
        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i + 1]}"
            if phrase not in seen_in_this:
                phrase_map.setdefault(phrase, []).append(issue)
                seen_in_this.add(phrase)
    filtered = [(p, iss) for p, iss in phrase_map.items() if len(iss) >= min_count]
    filtered.sort(key=lambda x: -len(x[1]))
    return filtered[:n]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    history  = load_history()
    last     = history.get("last_week", {})

    # Week label = last Mon–Sun (script runs Monday, reports on prior week)
    today       = datetime.now(ET)
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    week_label  = f"{last_monday.strftime('%b %d')} – {last_sunday.strftime('%b %d, %Y')}"

    # ------------------------------------------------------------------
    # Volume: all open tickets with the taxops label
    # ------------------------------------------------------------------
    all_issues = jira_search(
        f'{BASE_JQL} AND labels = "us-taxops-ticket"',
        fields=COMMON_FIELDS, max_results=500,
    )
    all_open = [i for i in all_issues
                if (i["fields"].get("status") or {}).get("name", "") not in OPEN_STATUSES_EXCLUDE]

    new_ops_tasks = jira_search(
        f'{BASE_JQL} AND created >= "-7d"',
        fields=["summary", "issuetype"],
    )
    new_tasks = jira_search(
        f'project = PF AND issuetype = Task AND created >= "-7d"',
        fields=["summary", "issuetype"],
    )
    resolved_this_week = jira_search(
        f'{BASE_JQL} AND status = Done AND updated >= "-7d"',
        fields=["summary"],
    )

    total_open      = len(all_open)
    total_new_ops   = len(new_ops_tasks)
    total_new_tasks = len(new_tasks)
    total_new       = total_new_ops + total_new_tasks
    total_resolved  = len(resolved_this_week)

    # ------------------------------------------------------------------
    # SLA / Priority: all open tickets
    # ------------------------------------------------------------------
    sla_breach_issues   = [i for i in all_open if "sla-breached"    in get_labels(i)]
    sla_approach_issues = [i for i in all_open if "sla-approaching" in get_labels(i)]
    highest_issues      = [i for i in all_open
                           if (i["fields"].get("priority") or {}).get("name", "") == "Highest"]
    n_sla_breach = len(sla_breach_issues)
    n_sla_app    = len(sla_approach_issues)
    n_highest    = len(highest_issues)

    # Escalations: tickets with taxops_escalation label
    escalation_issues = [i for i in all_open if "taxops_escalation" in get_labels(i)]
    n_escalations     = len(escalation_issues)

    # ------------------------------------------------------------------
    # Governance: tickets created since GOVERNANCE_START only
    # ------------------------------------------------------------------
    gov_issues_all = jira_search(
        f'{BASE_JQL} AND labels = "us-taxops-ticket" AND created >= "{GOVERNANCE_START}"',
        fields=COMMON_FIELDS, max_results=500,
    )
    gov_issues = [i for i in gov_issues_all
                  if (i["fields"].get("status") or {}).get("name", "") not in OPEN_STATUSES_EXCLUDE]

    qa_issues        = [i for i in gov_issues if "qa-incomplete"       in get_labels(i)]
    bad_label_issues = [i for i in gov_issues if "missing-labels"      in get_labels(i)]
    signoff_issues   = [i for i in gov_issues if "signoff-mismatch"    in get_labels(i)]
    wfo_24_issues    = [i for i in gov_issues if "waiting-for-ops-24h" in get_labels(i)]
    wfo_72_issues    = [i for i in gov_issues if "waiting-for-ops-72h" in get_labels(i)]

    n_qa         = len(qa_issues)
    n_labels_bad = len(bad_label_issues)
    n_signoff    = len(signoff_issues)
    n_wfo_24     = len(wfo_24_issues)
    n_wfo_72     = len(wfo_72_issues)

    # High Risk: unique tickets across Key Risk categories
    # (Highest priority OR WFO 72h OR SLA breached) — now safe, all three are defined
    high_risk_keys = (
        {i["key"] for i in highest_issues}
        | {i["key"] for i in wfo_72_issues}
        | {i["key"] for i in sla_breach_issues}
    )
    n_high_risk = len(high_risk_keys)

    # ------------------------------------------------------------------
    # Jira filter URLs (used when ticket count > 5)
    # ------------------------------------------------------------------
    jql_qa         = GOV_OPEN_FILTER_JQL + ' AND labels = "qa-incomplete"'
    jql_labels     = GOV_OPEN_FILTER_JQL + ' AND labels = "missing-labels"'
    jql_signoff    = GOV_OPEN_FILTER_JQL + ' AND labels = "signoff-mismatch"'
    jql_wfo_24     = GOV_OPEN_FILTER_JQL + ' AND labels = "waiting-for-ops-24h"'
    jql_wfo_72     = GOV_OPEN_FILTER_JQL + ' AND labels = "waiting-for-ops-72h"'
    jql_sla_app    = BASE_OPEN_FILTER_JQL + ' AND labels = "sla-approaching"'
    jql_sla_breach = BASE_OPEN_FILTER_JQL + ' AND labels = "sla-breached"'
    jql_highest    = BASE_OPEN_FILTER_JQL + ' AND priority = Highest'
    jql_escalation = BASE_OPEN_FILTER_JQL + ' AND labels = "taxops_escalation"'

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------
    flagged_issues = [i for i in gov_issues
                      if any(lbl in get_labels(i) for lbl in
                             ["qa-incomplete", "missing-labels", "signoff-mismatch", "sla-breached"])]

    tax_type_data = top_tax_types_with_issues(all_open)
    bigram_data   = top_bigrams_with_issues(flagged_issues)

    tax_lines = []
    for tax_type, issues in tax_type_data:
        jql = BASE_OPEN_FILTER_JQL + f' AND summary ~ "{tax_type}"'
        tax_lines.append(f"  • *{tax_type}* ({len(issues)}): {fmt_links(issues, jql)}")
    tax_str = "\n".join(tax_lines) if tax_lines else "  • None identified"

    bigram_lines = []
    for phrase, issues in bigram_data:
        jql = GOV_OPEN_FILTER_JQL + f' AND summary ~ "\\"{phrase}\\""'
        bigram_lines.append(f'  • *"{phrase}"* ({len(issues)}): {fmt_links(issues, jql)}')
    bigram_str = "\n".join(bigram_lines) if bigram_lines else "  • None identified"

    # ------------------------------------------------------------------
    # Key Risks
    # ------------------------------------------------------------------
    risks = []
    if n_highest > 0:
        risks.append(
            f"{n_highest} Highest priority ticket(s) unresolved: "
            f"{fmt_links(highest_issues, jql_highest)}"
        )
    if n_wfo_72 > 0:
        risks.append(
            f"{n_wfo_72} Waiting for Ops ticket(s) aged beyond 72 hours: "
            f"{fmt_links(wfo_72_issues, jql_wfo_72)}"
        )
    if n_sla_breach > 0:
        risks.append(
            f"{n_sla_breach} ticket(s) have breached SLA: "
            f"{fmt_links(sla_breach_issues, jql_sla_breach)}"
        )
    if not risks:
        risks.append("No critical risks identified this week.")
    risks_str = "\n".join(f"• {r}" for r in risks)

    # ------------------------------------------------------------------
    # Governance trend
    # ------------------------------------------------------------------
    total_gov = n_qa + n_labels_bad + n_signoff
    last_gov  = last.get("qa", 0) + last.get("labels", 0) + last.get("signoff", 0)

    if not last:
        gov_trend = "baseline established"
    elif total_gov < last_gov:
        gov_trend = f"improved from {last_gov} last week"
    elif total_gov > last_gov:
        gov_trend = f"up from {last_gov} last week"
    else:
        gov_trend = "unchanged from last week"

    # ------------------------------------------------------------------
    # Headline: 3-line structured format
    # ------------------------------------------------------------------
    line1 = f"*Weekly TaxOps Jira Governance Digest | Week of {week_label}*"

    intake_str = f"{total_new_ops} Ops - Customer Task"
    if total_new_tasks > 0:
        intake_str += f" | {total_new_tasks} Task 🚩"

    line2 = "\n".join([
        f"• Total Backlog: {total_open} Ops - Customer Task",
        f"• New Intake: {intake_str}",
        f"• Resolved: {total_resolved}",
        f"• Waiting for Ops: {n_wfo_24 + n_wfo_72}",
        f"• Highest Priority: {n_highest}",
        f"• Escalations: {n_escalations}",
        f"• High Risk: {n_high_risk}",
        f"• SLA Breaches: {n_sla_breach}",
    ])

    if total_new > total_resolved:
        backlog_assessment = (
            f"Backlog grew this week — {total_new} tickets in vs {total_resolved} resolved. "
            f"Engineering is not keeping pace with incoming volume."
        )
    elif total_resolved > total_new:
        backlog_assessment = (
            f"Backlog improved — {total_resolved} tickets resolved vs {total_new} new. "
            f"Engineering is outpacing intake."
        )
    else:
        backlog_assessment = (
            f"Intake and resolution balanced this week ({total_new} in, {total_resolved} out)."
        )

    if total_gov >= 5:
        gov_assessment = (
            f"{total_gov} governance flags detected — a Jira hygiene refresher is recommended for the team."
        )
    elif total_gov >= 2:
        gov_assessment = (
            f"{total_gov} governance flag{'s' if total_gov != 1 else ''} on new tickets — "
            f"targeted coaching on submission standards may be needed."
        )
    elif total_gov == 1:
        gov_assessment = "1 governance flag this week — minor coaching may be needed."
    else:
        gov_assessment = "Ticket quality is strong — no governance flags this week."

    line3 = f"{backlog_assessment} {gov_assessment}"

    headline = f"{line1}\n\n{line2}\n\n{line3}\n\n👇 Full breakdown in thread"

    # ------------------------------------------------------------------
    # Recommended Actions (dynamic)
    # ------------------------------------------------------------------
    actions = []
    if n_qa > 0 or n_labels_bad > 0 or n_signoff > 0:
        actions.append(
            f"• Region Leads: remediate incomplete QA tickets and labeling gaps. cc: {CC_REGION_LEADS}"
        )
    if n_sla_breach > 0 or n_sla_app > 0:
        actions.append(
            f"• Engineering & TaxOps: review breached and near-breach SLAs, align on resolution. cc: {CC_ENG_TAXOPS}"
        )
    if n_wfo_24 > 0 or n_wfo_72 > 0:
        actions.append(
            f"• Managers: intervene on Waiting for Ops items beyond response timelines. cc: {CC_MANAGERS}"
        )
    if bigram_data:
        actions.append(
            f"• Product & Engineering: assess recurring patterns, prioritize systemic fixes. cc: {CC_PRODUCT_ENG}"
        )
    if len(risks) > 1 or bigram_data or n_sla_breach > 0:
        actions.append(
            f"• Leadership: evaluate whether trends warrant process, tooling, or ownership changes. cc: {CC_LEADERSHIP}"
        )
    actions_str = "\n".join(actions) if actions else "• No actions required this week."

    # ------------------------------------------------------------------
    # Detail: full WBR breakdown (thread reply)
    # ------------------------------------------------------------------
    detail = (
        f"*Executive Summary*\n"
        f"{wow(total_open, last.get('open'))} open tickets "
        f"({total_new} new | {total_resolved} resolved this week). "
        f"{wow(n_sla_breach, last.get('sla_breach'))} SLA breach{'es' if n_sla_breach != 1 else ''}, "
        f"{n_sla_app} approaching threshold. "
        f"{n_wfo_24 + n_wfo_72} Waiting for Ops. "
        f"Governance: {total_gov} flag{'s' if total_gov != 1 else ''} ({gov_trend}).\n\n"

        f"*Quality Gate Issues* _(new tickets since {GOVERNANCE_START})_\n"
        f"• Incomplete QA: {n_qa} — {fmt_links(qa_issues, jql_qa)}\n\n"

        f"*Labeling / Routing Issues* _(new tickets since {GOVERNANCE_START})_\n"
        f"• Missing or invalid label quadrants: {n_labels_bad} — {fmt_links(bad_label_issues, jql_labels)}\n"
        f"• Sign-off mismatches: {n_signoff} — {fmt_links(signoff_issues, jql_signoff)}\n\n"

        f"*Waiting for Ops Aging*\n"
        f"• 24+ business hours with no response: {n_wfo_24} — {fmt_links(wfo_24_issues, jql_wfo_24)}\n"
        f"• 72+ hours with no response: {n_wfo_72} — {fmt_links(wfo_72_issues, jql_wfo_72)}\n\n"

        f"*Engineering SLA Watch*\n"
        f"• Approaching SLA: {n_sla_app} — {fmt_links(sla_approach_issues, jql_sla_app)}\n"
        f"• Breached SLA: {n_sla_breach} — {fmt_links(sla_breach_issues, jql_sla_breach)}\n\n"

        f"*Potential Trends and Bulk Issues*\n"
        f"_Recurring tax types (all open tickets):_\n"
        f"{tax_str}\n\n"
        f"_Common patterns in flagged tickets:_\n"
        f"{bigram_str}\n\n"

        f"*Key Risks*\n"
        f"{risks_str}\n\n"

        f"*Recommended Actions*\n"
        f"{actions_str}"
    )

    _req.post(
        SLACK_WEBHOOK_EXEC,
        json={"headline": headline, "detail": detail},
        headers={"Content-Type": "application/json"},
        timeout=30,
    ).raise_for_status()
    print("[A6] Posted weekly digest")

    save_history({
        "week_ending": datetime.now(ET).strftime("%Y-%m-%d"),
        "last_week": {
            "open":         total_open,
            "new":          total_new,
            "resolved":     total_resolved,
            "sla_breach":   n_sla_breach,
            "sla_approach": n_sla_app,
            "qa":           n_qa,
            "labels":       n_labels_bad,
            "signoff":      n_signoff,
            "wfo_24":       n_wfo_24,
            "wfo_72":       n_wfo_72,
        }
    })
    print("[A6] Saved WoW history")


if __name__ == "__main__":
    run()
