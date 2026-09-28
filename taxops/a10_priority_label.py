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


def summarize_labels(labels):
    if not labels:
        return "<none>"
    return ", ".join(sorted(labels))


def run():
    priority_names = "Highest, High, Medium, Low"
    excluded_labels = ", ".join(f'"p{i}_priority"' for i in range(10))
    jql = (
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} '
        f'AND priority in ({priority_names}) '
        f'AND labels not in ({excluded_labels})'
    )

    print(f"[A10] JQL: {jql}")
    print("[A10] Expected mapping: " + ", ".join(f"{k}->{v}" for k, v in PRIORITY_TO_LABEL.items()))

    issues = jira_search(
        jql,
        fields=["labels", "summary", "priority", "status", "issuetype", "project"],
        max_results=200,
    )
    keys = [issue.get("key", "<unknown>") for issue in issues]
    print(f"[A10] {len(issues)} eligible tickets missing a p#_priority label")
    print(f"[A10] Eligible ticket keys: {', '.join(keys) if keys else '<none>'}")

    fixed = 0
    skipped = 0
    for issue in issues:
        key = issue["key"]
        try:
            fields = issue.get("fields", {}) or {}
            current = get_labels(issue)
            priority = (fields.get("priority") or {}).get("name")
            mapped_label = PRIORITY_TO_LABEL.get(priority)
            status = (fields.get("status") or {}).get("name")
            issue_type = (fields.get("issuetype") or {}).get("name")
            project = (fields.get("project") or {}).get("key")

            print(
                f"[A10] Inspecting {key}: project={project}, issue_type={issue_type}, "
                f"status={status}, priority={priority}, labels={summarize_labels(current)}"
            )

            if has_priority_label(current):
                skipped += 1
                print(f"[A10] Skipping {key}: already has a p#_priority label")
                continue

            if not mapped_label:
                skipped += 1
                print(f"[A10] Skipping {key}: no mapping for priority={priority}")
                continue

            update_labels(key, current + [mapped_label])
            fixed += 1
            print(f"[A10] Added {mapped_label} to {key}")
        except Exception as e:
            post_error(f"A10 error on {key}: {e}")
            print(f"[A10] Error on {key}: {type(e).__name__}: {e}")

    print(f"[A10] Applied mapped priority label to {fixed} tickets; skipped {skipped}")


if __name__ == "__main__":
    run()
