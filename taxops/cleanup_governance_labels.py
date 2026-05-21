import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import time

LABELS_TO_REMOVE = ["qa-incomplete", "missing-labels", "signoff-mismatch"]

issues = jira_search(
    f'{BASE_JQL} AND created < "2026-05-18" AND labels in ("qa-incomplete", "missing-labels", "signoff-mismatch")',
    fields=["labels", "summary"],
    max_results=500,
)
print(f"Found {len(issues)} historical tickets with governance labels")

fixed = 0
for issue in issues:
    key = issue["key"]
    current = get_labels(issue)
    cleaned = [l for l in current if l not in LABELS_TO_REMOVE]
    if len(cleaned) != len(current):
        update_labels(key, cleaned)
        fixed += 1
        time.sleep(0.3)
        if fixed % 10 == 0:
            print(f"  {fixed} done...")

print(f"Done. Cleaned {fixed} tickets.")
