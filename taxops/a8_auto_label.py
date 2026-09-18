"""
A8 - Origin Label Report-Only Guard
Polling every 15 min.

Originating-team labels must be explicit. This script intentionally does not
add `us-taxops-ticket` or any other origin label, regardless of feature-flag
state, so missing or conflicting origin labels remain visible to the Quality Gate.
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


def run():
    print("[A8] origin labels must be explicit; no auto-stamping performed")


if __name__ == "__main__":
    run()
