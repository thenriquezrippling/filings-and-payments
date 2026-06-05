"""
A5 — Priority SLA Label Manager
Runs daily Mon–Fri at 9 AM UTC.

Manages sla-approaching and sla-breached labels + Jira comments.
NO Slack messages — SLA data is reported in the Monday A6 weekly digest only.

SLA targets (business days from ticket creation):
  Highest →  5 biz days (approaching at 4)
  High    → 10 biz days (approaching at 8)
  Medium  → 20 biz days (approaching at 16)
  Low     → 30 biz days (approaching at 25)

Dedup: AUTO_FLAG:SLA_APPROACHING, AUTO_FLAG:SLA_BREACHED
Labels: sla-approaching → sla-breached lifecycle.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SLA = {
    "Highest": (4,  5),
    "High":    (8,  10),
    "Medium":  (16, 20),
    "Low":     (25, 30),
}
DEFAULT_SLA = (16, 20)


def run():
    issues = jira_search(
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} AND labels = "us-taxops-ticket"',
        fields=COMMON_FIELDS,
        max_results=200,
    )
    print(f"[A5] Checking SLA on {len(issues)} open tickets")

    approaching, breached = [], []

    for issue in issues:
        key      = issue["key"]
        fields   = issue["fields"]
        labels   = get_labels(issue)
        priority = (fields.get("priority") or {}).get("name", "Medium")
        created  = fields.get("created", "")

        app_days, bre_days = SLA.get(priority, DEFAULT_SLA)
        elapsed = biz_days_since(created)

        try:
            if elapsed >= bre_days:
                breached.append((issue, key, labels, priority, elapsed, bre_days))
            elif elapsed >= app_days:
                approaching.append((issue, key, labels, priority, elapsed, app_days))
            else:
                _clean_sla_labels(issue, key, labels)
        except Exception as e:
            post_error(f"A5 error on {key}: {e}")

    _process_list(breached,    "AUTO_FLAG:SLA_BREACHED",    "sla-breached",    "sla-approaching")
    _process_list(approaching, "AUTO_FLAG:SLA_APPROACHING", "sla-approaching", None)

    print(f"[A5] Breached: {len(breached)} | Approaching: {len(approaching)}")


def _process_list(items, flag, add_lbl, remove_lbl):
    """Apply label and Jira comment only. No Slack — SLA data goes in A6 weekly digest."""
    for (issue, key, labels, priority, elapsed, threshold) in items:
        try:
            if has_auto_flag(key, flag):
                continue

            label_name = "SLA Breached" if "BREACHED" in flag else "SLA Approaching"
            add_comment(key,
                f"{flag} — {label_name}.\n\n"
                f"Priority: {priority} | Elapsed: {elapsed:.1f} biz days "
                f"| Threshold: {threshold} biz days."
            )
            add_label(issue, key, add_lbl)
            if remove_lbl and remove_lbl in labels:
                remove_label(issue, key, remove_lbl)

            print(f"[A5] {key} — {label_name} ({elapsed:.1f}/{threshold} biz days, {priority})")
        except Exception as e:
            post_error(f"A5 error processing {key}: {e}")


def _clean_sla_labels(issue, key, labels):
    for lbl in ("sla-approaching", "sla-breached"):
        if lbl in labels:
            remove_label(issue, key, lbl)


if __name__ == "__main__":
    run()
