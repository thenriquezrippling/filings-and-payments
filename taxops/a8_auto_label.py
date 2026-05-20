"""
A8 - Auto-Add Ownership Label
Polling every 15 min.

Silently adds `us-taxops-ticket` to any PF Ops-Customer-Task ticket
that is missing it. No Jira comment. No Slack message. Fully silent.
This label is permanent and is NEVER removed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

OWNERSHIP = "us-taxops-ticket"


def run():
    issues = jira_search(
        f'{BASE_JQL} AND labels not in ("{OWNERSHIP}")',
        fields=["labels", "summary"],
        max_results=200,
    )
    print(f"[A8] {len(issues)} tickets missing {OWNERSHIP}")

    fixed = 0
    for issue in issues:
        key = issue["key"]
        try:
            current = get_labels(issue)
            if OWNERSHIP not in current:
                update_labels(key, current + [OWNERSHIP])
                fixed += 1
        except Exception as e:
            post_error(f"A8 error on {key}: {e}")

    print(f"[A8] Applied {OWNERSHIP} to {fixed} tickets")


if __name__ == "__main__":
    run()
