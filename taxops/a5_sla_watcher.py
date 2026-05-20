"""
A5 — Priority SLA Watcher
Runs daily Mon–Fri at 9 AM UTC.

SLA targets (business days from ticket creation):
  Highest →  5 biz days (approaching at 4 = 80%)
  High    → 10 biz days (approaching at 8 = 80%)
  Medium  → 20 biz days (approaching at 16 = 80%)
  Low     → 30 biz days (approaching at 25, per spec)

Posts to CH_LEAD tagging region lead + Rana (NOT assignee).
Dedup: AUTO_FLAG:SLA_APPROACHING, AUTO_FLAG:SLA_BREACHED
Labels: sla-approaching → sla-breached lifecycle.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

# (approaching_days, breach_days)
SLA = {
    "Highest": (4,  5),
    "High":    (8,  10),
    "Medium":  (16, 20),
    "Low":     (25, 30),
}
DEFAULT_SLA = (16, 20)   # Medium fallback


def run():
    issues = jira_search(
        f'{BASE_JQL} AND status != Done AND labels = "us-taxops-ticket"',
        fields=COMMON_FIELDS,
        max_results=200,
    )
    print(f"[A5] Checking SLA on {len(issues)} open tickets")

    approaching, breached = [], []

    for issue in issues:
        key      = issue["key"]
        fields   = issue["fields"]
        summary  = fields.get("summary", "(no summary)")
        url      = issue_url(key)
        labels   = get_labels(issue)
        priority = (fields.get("priority") or {}).get("name", "Medium")
        created  = fields.get("created", "")

        app_days, bre_days = SLA.get(priority, DEFAULT_SLA)
        elapsed = biz_days_since(created)

        try:
            if elapsed >= bre_days:
                breached.append((issue, key, summary, url, labels, priority,
                                 elapsed, bre_days))
            elif elapsed >= app_days:
                approaching.append((issue, key, summary, url, labels, priority,
                                    elapsed, app_days))
            else:
                # Under threshold — clean up labels if present
                _clean_sla_labels(issue, key, labels)
        except Exception as e:
            post_error(f"A5 error on {key}: {e}")

    _process_list(breached,    "AUTO_FLAG:SLA_BREACHED",    "sla-breached",   "sla-approaching",
                  ":fire:",    "*SLA Breached*")
    _process_list(approaching, "AUTO_FLAG:SLA_APPROACHING", "sla-approaching", None,
                  ":warning:", "*SLA Approaching*")

    print(f"[A5] Breached: {len(breached)} | Approaching: {len(approaching)}")


def _process_list(items, flag, add_lbl, remove_lbl, emoji, title):
    for (issue, key, summary, url, labels, priority,
         elapsed, threshold) in items:
        try:
            if has_auto_flag(key, flag):
                continue

            comment_text = (
                f"{flag} — {title.strip('*')}.\n\n"
                f"Priority: {priority} | Elapsed: {elapsed:.1f} biz days "
                f"| Threshold: {threshold} biz days."
            )
            add_comment(key, comment_text)
            add_label(issue, key, add_lbl)
            if remove_lbl and remove_lbl in labels:
                remove_label(issue, key, remove_lbl)

            is_peo   = "e2e-peo" in labels
            lead_uid = region_lead_uid(labels, is_peo)
            lead_tag = f"<@{lead_uid}>" if lead_uid else ""
            rana_tag = f"<@{RANA_UID}>" if RANA_UID else "@TaxOps Lead"
            tags     = " ".join(t for t in [lead_tag, rana_tag] if t)

            slack_post(
                f"{emoji} {title} {tags} — <{url}|{key}>\n"
                f"{summary}\n"
                f"Priority: {priority} | {elapsed:.1f}/{threshold} biz days elapsed.",
                CH_LEAD,
            )
        except Exception as e:
            post_error(f"A5 error processing {key}: {e}")


def _clean_sla_labels(issue, key, labels):
    for lbl in ("sla-approaching", "sla-breached"):
        if lbl in labels:
            remove_label(issue, key, lbl)


if __name__ == "__main__":
    run()
