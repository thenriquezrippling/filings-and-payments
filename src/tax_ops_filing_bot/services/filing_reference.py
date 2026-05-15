"""Match epic child filing tickets (Quarterly / Monthly / Semi-Monthly) for linking.

Jira automation should create issue links (typically \"Relates to\") from the new
Blocker or Filing Exception to the matched child ticket for operational context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tax_ops_filing_bot.models.filing import (
    FILING_FREQUENCY_IDS,
    FilingFrequency,
    FilingIssueDraft,
    FilingPeriod,
    FilingYear,
    IssueType,
)


@dataclass(frozen=True)
class EpicChildIssue:
    """Minimal fields from Jira search / parent epic children."""

    key: str
    summary: str
    issue_type_name: str
    duedate: str | None = None


_FILING_CHILD_TYPES = frozenset(
    {
        IssueType.QUARTERLY.value,
        IssueType.MONTHLY.value,
        IssueType.SEMI_MONTHLY.value,
    }
)

# Substring hints for epic child summaries (not exhaustive).
_STATE_NAME_BY_ABBREV: dict[str, str] = {
    "pa": "pennsylvania",
    "ny": "new york",
    "tx": "texas",
    "ca": "california",
    "il": "illinois",
    "oh": "ohio",
    "nj": "new jersey",
    "fl": "florida",
}


def _state_matches(state: str | None, summary_l: str) -> bool:
    if not state:
        return False
    s = state.strip().lower()
    if len(s) == 2:
        if s in summary_l:
            return True
        full = _STATE_NAME_BY_ABBREV.get(s)
        if full and full in summary_l:
            return True
        return False
    return s in summary_l


def _period_tokens(period: FilingPeriod | None) -> frozenset[str]:
    if period is None:
        return frozenset()
    return frozenset(
        {
            period.value.lower(),
            period.value.replace("-", "").lower(),
            f"q{period.value[1].lower()}",
            f"q{period.value[1]}",
        }
    )


def _year_tokens(year: FilingYear | None) -> frozenset[str]:
    if year is None:
        return frozenset()
    y = year.value
    short = y[-2:]
    return frozenset({y, short})


def _score_child(draft: FilingIssueDraft, child: EpicChildIssue) -> int:
    if child.issue_type_name not in _FILING_CHILD_TYPES:
        return 0
    summary_l = child.summary.lower()
    score = 0

    if _state_matches(draft.state, summary_l):
        score += 3
    if draft.filing_unit_code and draft.filing_unit_code.lower() in summary_l:
        score += 4

    for tok in _period_tokens(draft.filing_period):
        if tok and tok in summary_l:
            score += 2
            break

    for ytok in _year_tokens(draft.year):
        if ytok in summary_l:
            score += 1

    freq = draft.filing_frequency
    if freq == FilingFrequency.QUARTERLY and "quarter" in summary_l:
        score += 2
    if freq == FilingFrequency.MONTHLY and "month" in summary_l:
        score += 2
    if freq == FilingFrequency.SEMI_MONTHLY and "semi" in summary_l:
        score += 2

    if draft.issue_agency_type and draft.issue_agency_type.lower() in summary_l:
        score += 1

    return score


def pick_related_filing_keys(
    draft: FilingIssueDraft,
    children: Sequence[EpicChildIssue],
    *,
    min_score: int = 4,
) -> list[str]:
    """Return best-matching child filing issue keys (FILING-nnnn), sorted by score."""
    scored: list[tuple[int, str]] = []
    for ch in children:
        s = _score_child(draft, ch)
        if s >= min_score:
            scored.append((s, ch.key))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [k for _, k in scored]


def enrich_draft_with_epic_children(
    draft: FilingIssueDraft,
    children: Sequence[EpicChildIssue],
    *,
    min_score: int = 4,
) -> FilingIssueDraft:
    """Attach related filing keys; copy child due date when draft has none."""
    keys = pick_related_filing_keys(draft, children, min_score=min_score)
    due = draft.due_date
    if due is None and len(keys) == 1:
        sole_key = keys[0]
        sole = next((c for c in children if c.key == sole_key), None)
        if sole is not None and sole.duedate:
            due = sole.duedate
    return draft.model_copy(
        update={
            "related_filing_issue_keys": keys,
            "due_date": due,
        }
    )


def jira_issue_link_payload(
    inward_key: str,
    outward_key: str,
    *,
    link_type_name: str = "Relates",
) -> dict:
    """Build JSON body for ``POST /rest/api/3/issueLink`` (Jira Cloud)."""
    return {
        "type": {"name": link_type_name},
        "inwardIssue": {"key": inward_key},
        "outwardIssue": {"key": outward_key},
    }


def filing_frequency_option_id(freq: FilingFrequency | None) -> str | None:
    """Jira Cloud option id for customfield_21650 when building create payload."""
    if freq is None:
        return None
    return FILING_FREQUENCY_IDS.get(freq)
