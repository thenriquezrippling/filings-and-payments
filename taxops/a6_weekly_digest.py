"""
A6 — Weekly Executive QA Digest
Runs every Monday at 17:00 UTC (12:00 PM ET).

Posts to CH_EXEC (#taxops-leadership):
  Message 1 (top-level): one-line headline with key counts
  Message 2 (thread reply): full breakdown — all sections

No LLM. All analysis is deterministic Python:
  - Status counts via JQL label queries
  - Word frequency in summaries (top 10 non-stopwords)
  - Label distribution
  - Flag lists
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from datetime import datetime
from collections import Counter
import re

STOPWORDS = {
    "the","a","an","and","or","for","in","on","at","to","of","is","are",
    "was","were","with","this","that","from","by","not","be","it","as",
    "we","i","s","re","has","have","had","will","can","do","did","does",
    "its","but","so","if","into","than","no","he","she","they","them",
    "our","you","your","all","new","per","get","via","need","also",
}


def top_words(summaries, n=10):
    counts = Counter()
    for s in summaries:
        for w in re.findall(r"\b[a-z]{4,}\b", s.lower()):
            if w not in STOPWORDS:
                counts[w] += 1
    return counts.most_common(n)


def count_by_label(issues, label_set):
    counts = Counter()
    for issue in issues:
        for lbl in get_labels(issue):
            if lbl in label_set:
                counts[lbl] += 1
    return counts


def run():
    week_label = datetime.now(ET).strftime("%B %d, %Y")

    # ─ All active tickets ────────────────────────────────────────────
    all_issues = jira_search(
        f'{BASE_JQL} AND labels = "us-taxops-ticket"',
        fields=COMMON_FIELDS,
        max_results=500,
    )
    open_issues = [i for i in all_issues
                   if (i["fields"].get("status") or {}).get("name", "") != "Done"]
    done_this_week = jira_search(
        f'{BASE_JQL} AND status = Done AND updated >= "-7d"',
        fields=COMMON_FIELDS,
    )

    # ─ Label flag counts ────────────────────────────────────────────
    FLAG_LABELS = [
        "qa-incomplete", "missing-labels", "signoff-mismatch",
        "sla-approaching", "sla-breached",
        "waiting-for-ops-24h", "waiting-for-ops-72h",
        "new-scope-detected",
    ]
    flag_counts = {}
    for lbl in FLAG_LABELS:
        issues_with = [i for i in open_issues if lbl in get_labels(i)]
        flag_counts[lbl] = len(issues_with)

    # ─ Status distribution ──────────────────────────────────────────
    status_counts = Counter()
    for i in open_issues:
        st = (i["fields"].get("status") or {}).get("name", "Unknown")
        status_counts[st] += 1

    # ─ Region distribution ─────────────────────────────────────────
    REGION_LABELS_LIST = [
        "west-region","south-region","northeast-region",
        "midwest-region","IRS-region","federal-region","pr-region",
    ]
    region_counts = count_by_label(open_issues, set(REGION_LABELS_LIST))

    # ─ Team distribution ───────────────────────────────────────────
    TEAM_LABELS = [
        "us-amendments","us-tax-filings",
        "e2e-peo","rip-direct","us-nhr",
    ]
    team_counts = count_by_label(open_issues, set(TEAM_LABELS))

    # ─ Word frequency ─────────────────────────────────────────────
    summaries = [i["fields"].get("summary", "") for i in open_issues]
    words     = top_words(summaries, n=10)

    # ─ Tickets needing attention (for detail sections) ─────────────
    def flagged(label, limit=5):
        items = [i for i in open_issues if label in get_labels(i)][:limit]
        return [f"  • <{issue_url(i['key'])}|{i['key']}> {i['fields'].get('summary','')[:60]}"
                for i in items]

    qa_lines    = flagged("qa-incomplete")
    lbl_lines   = flagged("missing-labels")
    wfo_lines   = flagged("waiting-for-ops-24h")
    sla_lines   = flagged("sla-approaching") + flagged("sla-breached")
    scope_lines = flagged("new-scope-detected")

    # ─ Compute totals for headline ───────────────────────────────
    total_open  = len(open_issues)
    total_done  = len(done_this_week)
    n_qa        = flag_counts["qa-incomplete"]
    n_sla       = flag_counts["sla-approaching"] + flag_counts["sla-breached"]
    n_wfo       = flag_counts["waiting-for-ops-24h"] + flag_counts["waiting-for-ops-72h"]

    # ─ Post Message 1: short headline ────────────────────────────
    headline = (
        f"📊 *TaxOps Weekly QA Digest — Week of {week_label}*\n"
        f"{total_open} open tickets | {total_done} closed this week | "
        f"{n_qa} QA flags | {n_sla} SLA flags | {n_wfo} WFO aging\n"
        f"_Full breakdown in thread ↓_"
    )
    import requests as _req
    _req.post(SLACK_WEBHOOK_EXEC, json={"headline": headline, "detail": detail}, headers={"Content-Type": "application/json"}, timeout=30).raise_for_status()

    # ─ Post Message 2: full detail in thread ─────────────────────
    def fmt_section(title, lines, empty_msg="None this week ✅"):
        body = "\n".join(lines) if lines else f"  {empty_msg}"
        return f"*{title}*\n{body}"

    status_str = " | ".join(
        f"{k}: {v}" for k, v in status_counts.most_common()
    ) or "No open tickets"
    region_str = " | ".join(
        f"{k.replace('-region','').title()}: {v}" for k, v in region_counts.most_common()
    ) or "No region data"
    team_str = " | ".join(
        f"{k}: {v}" for k, v in team_counts.most_common()
    ) or "No team data"
    words_str = ", ".join(f"{w} ({c})" for w, c in words) or "(no data)"

    detail = "\n\n".join([
        fmt_section("🔍 Quality Gate Issues",   qa_lines),
        fmt_section("🏷️ Label/Routing Issues", lbl_lines),
        fmt_section("⏳ Waiting-for-Ops Aging", wfo_lines),
        fmt_section("🔥 SLA Watch",             sla_lines),
        fmt_section("🔭 New Scope Detected", scope_lines),
        f"*📈 Status Distribution*\n  {status_str}",
        f"*🌎 Region Breakdown*\n  {region_str}",
        f"*👥 Team Breakdown*\n  {team_str}",
        f"*💬 Top Keywords in Summaries*\n  {words_str}",
    ])

    import requests as _req
    _req.post(SLACK_WEBHOOK_EXEC, json={"headline": headline, "detail": detail}, headers={"Content-Type": "application/json"}, timeout=30).raise_for_status()
    print("[A6] Posted digest with thread")


if __name__ == "__main__":
    run()
