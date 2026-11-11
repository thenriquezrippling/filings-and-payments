"""
A10 - Sync Priority Mapping Label
Polling every 15 min.
Runs after A8 ownership labeling (see run_polling_suite.sh).

Keeps the mapped `p#_priority` label aligned with Jira Priority for open PF
Ops-Customer-Task tickets that use Jira Priority values Highest, High, Medium,
or Low.

Normal Jira Priority mapping:
- Highest -> p1_priority
- High -> p2_priority
- Medium -> p3_priority
- Low -> p4_priority

No-downgrade behavior:
- If Jira Priority maps to a more urgent label, update the label upward.
- If an existing p1-p4 label is already more urgent than Jira Priority, keep the
  more urgent label and do not downgrade it.

Non-priority labels are preserved and exactly one mapped `p#_priority` label is kept.

`p0_priority` is treated as a protected manual override and is never removed or
replaced by this automation.
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

PRIORITY_LABEL_RE = re.compile(r"^p[1-4]_priority$")
PROTECTED_PRIORITY_LABELS = {"p0_priority"}
PRIORITY_LABEL_RANK = {
    "p1_priority": 1,
    "p2_priority": 2,
    "p3_priority": 3,
    "p4_priority": 4,
}


def is_priority_label(label):
    return bool(PRIORITY_LABEL_RE.match(label or ""))


def priority_labels(labels):
    return [label for label in labels if is_priority_label(label)]


def has_protected_priority_label(labels):
    return any(label in PROTECTED_PRIORITY_LABELS for label in labels)


def protected_priority_labels(labels):
    return [label for label in labels if label in PROTECTED_PRIORITY_LABELS]


def most_urgent_priority_label(labels):
    candidates = [label for label in labels if is_priority_label(label)]
    if not candidates:
        return None
    return min(candidates, key=lambda label: PRIORITY_LABEL_RANK[label])


def desired_priority_label(labels, mapped_label):
    existing = most_urgent_priority_label(labels)
    if not existing:
        return mapped_label
    if PRIORITY_LABEL_RANK[existing] < PRIORITY_LABEL_RANK[mapped_label]:
        return existing
    return mapped_label


def synced_labels(labels, desired_label):
    non_priority_labels = [label for label in labels if not is_priority_label(label)]
    if desired_label not in non_priority_labels:
        non_priority_labels.append(desired_label)
    return non_priority_labels


def summarize_labels(labels):
    if not labels:
        return "<none>"
    return ", ".join(sorted(labels))


def run():
    priority_names = "Highest, High, Medium, Low"
    jql = (
        f'{BASE_JQL} AND {JQL_OPEN_ONLY} '
        f'AND priority in ({priority_names})'
    )

    print(f"[A10] JQL: {jql}")
    print("[A10] Jira Priority mapping with no-downgrade protection for existing p1-p4 labels")
    print("[A10] Expected mapping: " + ", ".join(f"{k}->{v}" for k, v in PRIORITY_TO_LABEL.items()))

    issues = jira_search(
        jql,
        fields=["labels", "summary", "priority", "status", "issuetype", "project"],
        max_results=200,
    )
    keys = [issue.get("key", "<unknown>") for issue in issues]
    print(f"[A10] {len(issues)} open tickets with mapped Jira priority")
    print(f"[A10] Candidate ticket keys: {', '.join(keys) if keys else '<none>'}")

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
            existing_priority_labels = priority_labels(current)
            existing_protected_priority_labels = protected_priority_labels(current)

            print(
                f"[A10] Inspecting {key}: project={project}, issue_type={issue_type}, "
                f"status={status}, jira_priority={priority}, expected_label={mapped_label}, "
                f"priority_labels={summarize_labels(existing_priority_labels)}, "
                f"protected_priority_labels={summarize_labels(existing_protected_priority_labels)}, "
                f"all_labels={summarize_labels(current)}"
            )

            if has_protected_priority_label(current):
                skipped += 1
                print(
                    f"[A10] Skipping {key}: protected manual priority label present "
                    f"({summarize_labels(existing_protected_priority_labels)})"
                )
                continue

            if not mapped_label:
                skipped += 1
                print(f"[A10] Skipping {key}: no mapping for priority={priority}")
                continue

            desired_label = desired_priority_label(current, mapped_label)
            updated = synced_labels(current, desired_label)
            if set(updated) == set(current) and len(updated) == len(current):
                skipped += 1
                if desired_label != mapped_label:
                    print(
                        f"[A10] Skipping {key}: preserving more urgent priority label "
                        f"{desired_label} over Jira Priority {priority}/{mapped_label}"
                    )
                else:
                    print(f"[A10] Skipping {key}: already synced to Jira Priority {priority}/{mapped_label}")
                continue

            update_labels(key, updated)
            fixed += 1
            action = "preserved more urgent existing label" if desired_label != mapped_label else "synced to Jira Priority"
            print(
                f"[A10] Synced {key}: action={action}, Jira Priority={priority}, "
                f"mapped_label={mapped_label}, desired_label={desired_label}, "
                f"old_priority_labels={summarize_labels(existing_priority_labels)}, "
                f"new_labels={summarize_labels(updated)}"
            )
        except Exception as e:
            post_error(f"A10 error on {key}: {e}")
            print(f"[A10] Error on {key}: {type(e).__name__}: {e}")

    print(f"[A10] Synced priority label on {fixed} tickets; skipped {skipped}")


if __name__ == "__main__":
    run()
