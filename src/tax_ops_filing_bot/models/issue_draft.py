"""Filing issue draft model — the structured output from LLM inference."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class IssuePriority(str, Enum):
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    LOWEST = "Lowest"


class IssueType(str, Enum):
    """Work Type values configured in the FILING Jira project."""

    BLOCKER = "Blocker"
    FILING_EXCEPTION = "Filing Exception"
    FEATURE_REQUEST = "Feature Request"
    RETRO = "Retro"
    EXECUTIVE_SUMMARY = "Executive Summary"


# ---------------------------------------------------------------------------
# Deterministic epic mapping: keywords/patterns → parent epic key
# ---------------------------------------------------------------------------

EPIC_MAP: dict[str, str] = {
    "eit": "FILING-101",
    "earned income tax": "FILING-101",
    "local tax": "FILING-101",
    "municipal tax": "FILING-101",
    "state filing": "FILING-200",
    "quarterly filing": "FILING-200",
    "q1 filing": "FILING-200",
    "q2 filing": "FILING-200",
    "q3 filing": "FILING-200",
    "q4 filing": "FILING-200",
    "federal filing": "FILING-300",
    "annual filing": "FILING-300",
    "amendment": "FILING-400",
    "amended return": "FILING-400",
    "penalty": "FILING-500",
    "notice": "FILING-500",
}


def resolve_parent_epic(text: str) -> Optional[str]:
    """Return the epic key for the first matching keyword in *text*, or None."""
    lower = text.lower()
    for keyword, epic_key in EPIC_MAP.items():
        if keyword in lower:
            return epic_key
    return None


# ---------------------------------------------------------------------------
# Deterministic label generation from thread/summary text
# ---------------------------------------------------------------------------

LABEL_RULES: list[tuple[str, str]] = [
    (r"\beit\b", "local-tax"),
    (r"\bearned income tax\b", "local-tax"),
    (r"\bpittsburgh\b", "pittsburgh"),
    (r"\bphiladelphia\b", "philadelphia"),
    (r"\bstate[- ]filing\b", "state-filing"),
    (r"\bfederal\b", "federal"),
    (r"\bq[1-4]\b", "quarterly"),
    (r"\bquarterly\b", "quarterly"),
    (r"\bamendment\b", "amendment"),
    (r"\bamended\b", "amendment"),
    (r"\bpenalty\b", "penalty"),
    (r"\bnotice\b", "notice"),
    (r"\bblocking\b", "blocker"),
    (r"\bblocked\b", "blocker"),
    (r"\bdeadline\b", "deadline"),
    (r"\burgent\b", "urgent"),
]


def generate_labels(text: str) -> list[str]:
    """Return a sorted, deduplicated list of labels derived from *text*."""
    lower = text.lower()
    labels: set[str] = set()
    for pattern, label in LABEL_RULES:
        if re.search(pattern, lower):
            labels.add(label)
    return sorted(labels)


# ---------------------------------------------------------------------------
# Implementation-note filtering for descriptions
# ---------------------------------------------------------------------------

_IMPL_NOTE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^[ \t]*(?:implementation|impl)[ \t]*notes?[:\-].*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"(?s)<!--.*?-->"),
    re.compile(r"^[ \t]*(?:TODO|FIXME|HACK|XXX)[:\s].*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^[ \t]*\[internal\].*$", re.IGNORECASE | re.MULTILINE),
]


def strip_implementation_notes(description: str) -> str:
    """Remove implementation notes, HTML comments, and internal markers."""
    result = description
    for pat in _IMPL_NOTE_PATTERNS:
        result = pat.sub("", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Deterministic work-type classification
# ---------------------------------------------------------------------------

_BLOCKER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bblocking\b", re.IGNORECASE),
    re.compile(r"\bblocked\b", re.IGNORECASE),
    re.compile(r"\bblock(?:er)?\b", re.IGNORECASE),
    re.compile(r"\bcannot file\b", re.IGNORECASE),
    re.compile(r"\bcan't file\b", re.IGNORECASE),
    re.compile(r"\bunable to (?:file|submit)\b", re.IGNORECASE),
    re.compile(r"\bdeadline\b", re.IGNORECASE),
    re.compile(r"\beit\b", re.IGNORECASE),
    re.compile(r"\bpenalty\b", re.IGNORECASE),
]

_FILING_EXCEPTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bexception\b", re.IGNORECASE),
    re.compile(r"\berror.{0,20}(?:filing|submission)\b", re.IGNORECASE),
    re.compile(r"\bfiling.{0,20}(?:error|fail)\b", re.IGNORECASE),
    re.compile(r"\brejected?\b", re.IGNORECASE),
    re.compile(r"\bmismatch\b", re.IGNORECASE),
]

_FEATURE_REQUEST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bfeature\s+request\b", re.IGNORECASE),
    re.compile(r"\benhancement\b", re.IGNORECASE),
    re.compile(r"\bwould be nice\b", re.IGNORECASE),
    re.compile(r"\bcan we add\b", re.IGNORECASE),
    re.compile(r"\bnew (?:feature|capability)\b", re.IGNORECASE),
]

_RETRO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bretro(?:spective)?\b", re.IGNORECASE),
    re.compile(r"\bpost[- ]?mortem\b", re.IGNORECASE),
    re.compile(r"\blessons?\s+learned\b", re.IGNORECASE),
    re.compile(r"\broot\s+cause\b", re.IGNORECASE),
]

_EXECUTIVE_SUMMARY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bexecutive\s+summary\b", re.IGNORECASE),
    re.compile(r"\bexec\s+summary\b", re.IGNORECASE),
    re.compile(r"\bstatus\s+report\b", re.IGNORECASE),
    re.compile(r"\bweekly\s+(?:update|report)\b", re.IGNORECASE),
]


def classify_work_type(text: str) -> IssueType:
    """Deterministically classify text into a FILING Work Type.

    Priority order: Blocker > Filing Exception > Retro > Feature Request > Executive Summary.
    Falls back to Blocker if no pattern matches (fail-safe for ops).
    """
    for pat in _BLOCKER_PATTERNS:
        if pat.search(text):
            return IssueType.BLOCKER
    for pat in _FILING_EXCEPTION_PATTERNS:
        if pat.search(text):
            return IssueType.FILING_EXCEPTION
    for pat in _RETRO_PATTERNS:
        if pat.search(text):
            return IssueType.RETRO
    for pat in _FEATURE_REQUEST_PATTERNS:
        if pat.search(text):
            return IssueType.FEATURE_REQUEST
    for pat in _EXECUTIVE_SUMMARY_PATTERNS:
        if pat.search(text):
            return IssueType.EXECUTIVE_SUMMARY
    return IssueType.BLOCKER


class FilingIssueDraft(BaseModel):
    """LLM-inferred Jira issue fields for the FILING project."""

    summary: str = Field(max_length=255, description="Jira issue summary / title")
    description: str = Field(description="Jira issue description (markdown)")
    issue_type: IssueType = Field(default=IssueType.BLOCKER)
    priority: IssuePriority = Field(default=IssuePriority.MEDIUM)
    labels: list[str] = Field(default_factory=list)
    parent_key: Optional[str] = Field(
        default=None,
        description="Epic key if the issue should be a child (e.g. 'FILING-101')",
    )
    assignee_hint: Optional[str] = Field(
        default=None,
        description="Slack username or display name the LLM thinks should own this",
    )

    @field_validator("description", mode="before")
    @classmethod
    def _clean_description(cls, v: str) -> str:
        return strip_implementation_notes(v) if isinstance(v, str) else v
