"""
A6 — Weekly Executive QA Digest
Runs every Monday at 12:00 PM ET (16:00 UTC).

Posts to CH_EXEC (#taxops-leadership):
  headline: one-line summary
  detail: full breakdown per WBR spec (in thread)

WoW comparison stored in taxops/wbr_history.json.
Governance metrics only cover tickets created >= GOVERNANCE_START.
SLA and volume metrics cover ALL open tickets.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from datetime import datetime
from collections import Counter
import requests as _req

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "wbr_history.json")

TAX_TYPES = ["SUI","FML","FUTA","SUTA","941","940","W-2","1099",
             "SDI","SIT","FIT","FICA","local"]
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

CC_REGION_LEADS = "<@U031NBG0E82> <@U026W3ACSU8>"
CC_ENG_TAXOPS   = "<@U026W3CCKLG> <@U026LRKHS1F>"
CC_MANAGERS     = "<!subteam^S06URQSJGEN>"
CC_PRODUCT_ENG  = "<@U026LRKHS1F> <@U026W3CCKLG> <@U01F7MRSW5V>"
CC_LEADERSHIP   = "<!subteam^S0ANS8X2B7Y>"


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
        return f"{current} (up {diff} WoW)"
    elif diff < 0:
        return f"{current} (down {abs(diff)} WoW)"
    return f"{current} (no change WoW)"


def top_tax_types(summaries, n=5):
    counts = Counter()
    for s in summaries:
        for m in TAX_RE.findall(s):
            counts[m.upper()] += 1
    return counts.most_common(n)


def top_bigrams(summaries, n=5):
    counts = Counter()
    for s in summaries:
        words = [w for w in re.findall(r'\b[a-z]{4,}\b', s.lower())
                 if w not in STOPWORDS and w not in NOISE]
        for i in range(len(words) - 1):
            counts[f"{words[i]} {words[i+1]}"] += 1
    return [(p, c) for p, c in counts.most_common(n * 2) if c >= 2][:n]


def detect_bulk_issues(issues, min_count=3):
    phrase_counts = Counter()
    for issue in issues:
        summary = issue["fields"].get("summary", "").lower()
        words = [w for w in re.findall(r'\b[a-z]{4,}\b', summary)
                 if w not in STOPWORDS and w not in NOISE]
        for i in range(len(words) - 1):
            phrase_counts[f"{words[i]} {words[i+1]}"] += 1
    return [(p, c) for p, c in phrase_counts.most_common(5) if c >= min_count]


def fmt_examples(issues, limit=3):
    return " ".join(f"<{issue_url(i['key'])}|{i['key']}>" for i in issues[:limit])


def run():
    history = load_history()
    last = history.get("last_week", {})
    week_label = datetime.now(ET).strftime("%B %d, %Y")

    # Volume: all open tickets
    all_open = jira_search(
        f'{BASE_JQL} AND status not in (Done, Closed, Resolved)',
        fields=COMMON_FIELDS, max_results=500,
    )
    new_this_week = jira_search(
        f'{BASE_JQL} AND created >= "-7d"',
        fields=["summary"],
    )
    resolved_this_week = jira_search(
        f'{BASE_JQL} AND status = Done AND updated >= "-7d"',
        fields=["summary"],
    )

    total_open     = len(all_open)
    total_new      = len(new_this_week)
    total_resolved = len(resolved_this_week)

    # SLA: all open tickets
    sla_breach_issues  = [i for i in all_open if "sla-breached" in get_labels(i)]
    sla_approach_issues = [i for i in all_open if "sla-approaching" in get_labels(i)]
    highest_issues     = [i for i in all_open
                          if (i["fields"].get("priority") or {}).get("name", "") == "Highest"]
    n_sla_breach = len(sla_breach_issues)
    n_sla_app    = len(sla_approach_issues)
    n_highest    = len(highest_issues)

    # Governance: tickets since GOVERNANCE_START only
    gov_issues = jira_search(
        f'{BASE_JQL} AND status not in (Done, Closed, Resolved) AND created >= "{GOVERNANCE_START}"',
        fields=COMMON_FIELDS, max_results=500,
    )

    def gov_count(label):
        return sum(1 for i in gov_issues if label in get_labels(i))

    n_qa         = gov_count("qa-incomplete")
    n_labels_bad = gov_count("missing-labels")
    n_signoff    = gov_count("signoff-mismatch")
    n_wfo_24     = gov_count("waiting-for-ops-24h")
    n_wfo_72     = gov_count("waiting-for-ops-72h")

    wfo_72_issues = [i for i in gov_issues if "waiting-for-ops-72h" in get_labels(i)]

    # Trends analysis
    all_summaries     = [i["fields"].get("summary", "") for i in all_open]
    flagged_summaries = [i["fields"].get("summary", "") for i in gov_issues
                         if any(l in get_labels(i) for l in
                                ["qa-incomplete", "missing-labels", "signoff-mismatch", "sla-breached"])]
    tax_types   = top_tax_types(all_summaries)
    root_bigrams = top_bigrams(flagged_summaries)
    bulk_issues = detect_bulk_issues(all_open)
    tax_str   = ", ".join(f"{t} ({c})" for t, c in tax_types)  or "None identified"
    root_str  = ", ".join(f"{p} ({c})" for p, c in root_bigrams) or "None identified"
    bulk_str  = "; ".join(f'"{p}" - {c} tickets' for p, c in bulk_issues) or "None identified"

    # Key Risks with examples
    risks = []
    if n_highest > 0:
        risks.append(
            f"{n_highest} Highest priority ticket(s) remain unresolved. "
            f"Examples: {fmt_examples(highest_issues)}"
        )
    if n_wfo_72 > 0:
        risks.append(
            f"{n_wfo_72} Waiting for Ops ticket(s) aged beyond 72 hours. "
            f"Examples: {fmt_examples(wfo_72_issues)}"
        )
    if n_sla_breach > 0:
        risks.append(
            f"{n_sla_breach} ticket(s) have breached SLA thresholds. "
            f"Examples: {fmt_examples(sla_breach_issues)}"
        )
    if not risks:
        risks.append("No critical risks identified this week.")
    risks_str = "\n".join(f"- {r}" for r in risks)

    # Executive Summary
    total_gov = n_qa + n_labels_bad + n_signoff
    last_gov  = last.get("qa", 0) + last.get("labels", 0) + last.get("signoff", 0)
    if not last:
        trend_line = "first tracked week - baseline established."
    elif total_gov < last_gov:
        trend_line = f"improved from {last_gov} flag(s) last week."
    elif total_gov > last_gov:
        trend_line = f"increased from {last_gov} flag(s) last week."
    else:
        trend_line = "unchanged from last week."

    exec_summary = (
        f"Overall Jira governance shows {total_gov} open flag(s) across new tickets "
        f"({trend_line}) "
        f"{n_sla_breach} ticket(s) have breached SLA and {n_sla_app} are approaching threshold. "
        f"{n_wfo_24} ticket(s) are Waiting for Ops beyond 24 hours."
    )

    # Headline (top-level post)
    headline = (
        f"Weekly TaxOps Jira Governance Digest - Week of {week_label}\n"
        f"{wow(total_open, last.get('open'))} open | "
        f"{total_new} new | "
        f"{wow(n_sla_breach, last.get('sla_breach'))} SLA breached | "
        f"{n_wfo_24 + n_wfo_72} Waiting for Ops"
    )

    # Detail (thread reply)
    detail = (
        f"*Executive Summary*\n{exec_summary}\n\n"
        f"*Quality Gate Issues* _(new tickets since {GOVERNANCE_START})_\n"
        f"- Total incomplete tickets: {n_qa}\n\n"
        f"*Labeling / Routing Issues* _(new tickets since {GOVERNANCE_START})_\n"
        f"- Missing or invalid label quadrants: {n_labels_bad}\n"
        f"- Sign-off mismatches: {n_signoff}\n\n"
        f"*Waiting for Ops Aging*\n"
        f"- 24+ business hours with no response: {n_wfo_24}\n"
        f"- 72+ hours with no response: {n_wfo_72}\n\n"
        f"*Engineering SLA Watch*\n"
        f"- Approaching SLA: {n_sla_app}\n"
        f"- Breached SLA: {n_sla_breach}\n\n"
        f"*Potential Trends and Bulk Issues*\n"
        f"- Common root causes: {root_str}\n"
        f"- Repeated tax types: {tax_str}\n"
        f"- Bulk issues impacting multiple clients: {bulk_str}\n\n"
        f"*Key Risks*\n{risks_str}\n\n"
        f"*Recommended Actions*\n"
        f"- Region Leads to remediate incomplete Quality Gate tickets and labeling gaps "
        f"to improve Engineering readiness. cc: {CC_REGION_LEADS}\n"
        f"- Engineering and TaxOps to review breached and near-breach SLAs and align on "
        f"resolution plans for highest-risk items. cc: {CC_ENG_TAXOPS}\n"
        f"- TaxOps managers to intervene on Waiting for Ops items aged beyond established "
        f"response timelines. cc: {CC_MANAGERS}\n"
        f"- Product and Engineering to assess recurring themes and prioritize systemic fixes "
        f"for bulk issues affecting multiple customers. cc: {CC_PRODUCT_ENG}\n"
        f"- Leadership to evaluate whether emerging trends warrant process, tooling, or "
        f"ownership changes. cc: {CC_LEADERSHIP}"
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
