"""
A10 - Sync Priority Mapping Label
Polling every 15 min.
Runs after A8 ownership labeling (see run_polling_suite.sh).

Keeps Jira Priority and the mapped `p#_priority` label aligned for open PF
Ops-Customer-Task tickets that use Jira Priority values Highest, High, Medium,
or Low.

Priority labels use the more urgent signal:
- If Jira Priority is more urgent than the existing `p#_priority` label, update
  the label to match Jira Priority.
- If an existing `p#_priority` label is more urgent than Jira Priority, keep that
  more urgent label and update Jira Priority upward to match it.

Non-priority labels are preserved and exactly one mapped `p#_priority` label is kept.
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

LABEL_TO_PRIORITY = {label: priority for priority, label in PRIORITY_TO_LABEL.items()}

PRIORITY_RANK = {
    "Highest": 1,
    "High": 2,
    "Medium": 3,
    "Low": 4,
}

PRIORITY_LABEL_RE = re.compile(r"^p([1-4])_priority$")


def is_priority_label(label):
    return bool(PRIORITY_LABEL_RE.match(label or ""))


def priority_label_rank(label):
    match = PRIORITY_LABEL_RE.match(label or "")
    return int(match.group(1)) if match else None


def priority_labels(labels):
    return [label for label in labels if is_priority_label(label)]


def most_urgent_priority_label(labels):
    existing = priority_labels(labels)
    if not existing:
        return None
    return min(existing, key=priority_label_rank)


def choose_target(priority, labels):
    """
    Return (target_priority, target_label, reason).

    If Jira Priority is more urgent, sync the label down to Jira Priority.
    If an existing p# label is more urgent, keep that label and move Jira Priority up.
    """
    mapped_label = PRIORITY_TO_LABEL.get(priority)
    if not mapped_label:
        return None, None, f"no mapping for priority={priority}"

    label_candidate = most_urgent_priority_label(labels)
    if not label_candidate:
        return priority, mapped_label, "no existing priority label"

    label_priority = LABEL_TO_PRIORITY.get(label_candidate)
    if not label_priority:
        return priority, mapped_label, f"unrecognized existing priority label={label_candidate}"

    jira_rank = PRIORITY_RANK[priority]
    label_rank = priority_label_rank(label_candidate)

    if label_rank < jira_rank:
        return label_priority, label_candidate, "existing label is more urgent than Jira Priority"

    return priority, mapped_label, "Jira Priority is same or more urgent than existing label"


def synced_labels(labels, target_label):
    non_priority_labels = [label for label in labels if not is_priority_label(label)]
    if target_label not in non_priority_labels:
        non_priority_labels.append(target_label)
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
            current_priority = (fields.get("priority") or {}).get("name")
            status = (fields.get("status") or {}).get("name")
            issue_type = (fields.get("issuetype") or {}).get("name")
            project = (fields.get("project") or {}).get("key")
            existing_priority_labels = priority_labels(current)

            target_priority, target_label, reason = choose_target(current_priority, current)

            print(
                f"[A10] Inspecting {key}: project={project}, issue_type={issue_type}, "
                f"status={status}, jira_priority={current_priority}, "
                f"priority_labels={summarize_labels(existing_priority_labels)}, "
                f"target_priority={target_priority}, target_label={target_label}, reason={reason}, "
                f"all_labels={summarize_labels(current)}"
            )

            if not target_priority or not target_label:
                skipped += 1
                print(f"[A10] Skipping {key}: {reason}")
                continue

            updated_labels = synced_labels(current, target_label)
            labels_already_synced = set(updated_labels) == set(current) and len(updated_labels) == len(current)
            priority_already_synced = current_priority == target_priority

            if labels_already_synced and priority_already_synced:
                skipped += 1
                print(f"[A10] Skipping {key}: already synced to {target_priority}/{target_label}")
                continue

            if not priority_already_synced:
                update_priority(key, target_priority)
                print(f"[A10] Updated Jira Priority on {key}: {current_priority} -> {target_priority}")

            if not labels_already_synced:
                update_labels(key, updated_labels)
                print(
                    f"[A10] Updated priority label on {key}: "
                    f"old_priority_labels={summarize_labels(existing_priority_labels)}, "
                    f"new_label={target_label}"
                )

            fixed += 1
        except Exception as e:
            post_error(f"A10 error on {key}: {e}")
            print(f"[A10] Error on {key}: {type(e).__name__}: {e}")

    print(f"[A10] Synced priority/label on {fixed} tickets; skipped {skipped}")


if __name__ == "__main__":
    run()
