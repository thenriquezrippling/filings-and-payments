"""
A10 - Auto-Add Priority Mapping Label
Polling every 15 min.
Runs after A8 ownership labeling (see run_polling_suite.sh).

Silently adds the mapped `p#_priority` label to open PF Ops-Customer-Task tickets
that still use Jira Priority values Highest, High, Medium, or Low and do not already
have any `p#_priority` label.

Existing labels are preserved. Existing `p#_priority` labels are never removed or replaced.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

PRIORITY_TO_LABEL = {
    "Highest": "p1_priority",
    "High": "p2_priority",
    "Medium": "p3_priority",
    "Low": "p4_priority",
}

PRIORITY_LABEL_RE = re.compile(r"^p\d+_priority$")


def has_priority_label(labels):
    return any(PRIORITY_LABEL_RE.match(label or "") for label in labels)


def run():
    priority_names = "Highest, High, Medium, Low"
    excluded_labels = ", ".join(f'"p{i}_priority"' for i in range(10))

    issues = jira_search(
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} '
        f'AND priority in ({priority_names}) '
        f'AND labels not in ({excluded_labels})',
        fields=["labels", "summary", "priority"],
        max_results=200,
    )
    print(f"[A10] {len(issues)} eligible tickets missing a p#_priority label")

    fixed = 0
    skipped = 0
    for issue in issues:
        key = issue["key"]
        try:
            current = get_labels(issue)
            if has_priority_label(current):
                skipped += 1
                continue

            priority = (issue.get("fields", {}).get("priority") or {}).get("name")
            mapped_label = PRIORITY_TO_LABEL.get(priority)
            if not mapped_label:
                skipped += 1
                continue

            update_labels(key, current + [mapped_label])
            fixed += 1
        except Exception as e:
            post_error(f"A10 error on {key}: {e}")

    print(f"[A10] Applied mapped priority label to {fixed} tickets; skipped {skipped}")


if __name__ == "__main__":
    run()
