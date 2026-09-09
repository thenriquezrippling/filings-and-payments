"""
A8 - Auto-Add Ownership Label
Polling every 15 min.
Runs first in each polling cycle (see run_polling_suite.sh).

Silently adds `us-taxops-ticket` only to PF Ops-Customer-Task tickets
that already have at least one approved TaxOps classification label.
No Jira comment. No Slack message. Fully silent.
Downstream scripts (A1–A7, A9) scope to tickets with this label.
This label is permanent and is NEVER removed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

OWNERSHIP = "us-taxops-ticket"

WORKSTREAM_LABELS = {
    "NoticeQueue_task",
    "new_hire_reporting",
    "taxnoticebugfix",
    "Amendment_task",
    "Filing_task",
}

REGION_LABELS = {
    "west-region",
    "south-region",
    "midwest-region",
    "northeast-region",
    "IRS-region",
    "federal-region",
    "pr-region",
    "filings-amendments-region",
}

TEAM_LABELS = {
    "us-amendments",
    "e2e-peo",
    "rip-direct",
    "us-nhr",
    "us-filings",
}

APPROVED_TAXOPS_LABELS = WORKSTREAM_LABELS | REGION_LABELS | TEAM_LABELS


def has_any_approved_taxops_label(labels):
    return bool(set(labels) & APPROVED_TAXOPS_LABELS)


def _labels_any(allowed_labels):
    return "(" + " OR ".join(
        f'labels = "{label}"' for label in sorted(allowed_labels)
    ) + ")"


def run():
    issues = jira_search(
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} '
        f'AND labels not in ("{OWNERSHIP}") '
        f'AND {_labels_any(APPROVED_TAXOPS_LABELS)}',
        fields=["labels", "summary"],
        max_results=200,
    )
    print(f"[A8] {len(issues)} eligible tickets missing {OWNERSHIP}")

    fixed = 0
    skipped = 0
    for issue in issues:
        key = issue["key"]
        try:
            current = get_labels(issue)
            if OWNERSHIP not in current and has_any_approved_taxops_label(current):
                update_labels(key, current + [OWNERSHIP])
                fixed += 1
            else:
                skipped += 1
        except Exception as e:
            post_error(f"A8 error on {key}: {e}")

    print(f"[A8] Applied {OWNERSHIP} to {fixed} tickets; skipped {skipped}")


if __name__ == "__main__":
    run()
