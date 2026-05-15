"""Match epic child filing tickets (Quarterly / Monthly / Semi-Monthly) for linking.

Matching rules:
  - Slack thread title must have very high similarity to child Jira summary.
  - Filing unit code match is required when the draft has one; mismatches skip.
  - If multiple candidates tie or no strong match exists, do NOT auto-link
    and set needs_mapping_review = true.
  - Due date comes from the matched child ticket, not the LLM.
  - Year matching contributes to score only once (no double-counting).
  - State matching uses word boundaries to avoid substring false positives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
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

_STATE_NAME_BY_ABBREV: dict[str, str] = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york",
    "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}

_ABBREV_BY_STATE_NAME: dict[str, str] = {v: k for k, v in _STATE_NAME_BY_ABBREV.items()}


def _state_matches(state: str | None, summary_l: str) -> bool:
    """Match state using word boundaries — 'PA' must not match 'payroll'."""
    if not state:
        return False
    s = state.strip().lower()
    if len(s) == 2:
        if re.search(rf"\b{re.escape(s)}\b", summary_l):
            return True
        full = _STATE_NAME_BY_ABBREV.get(s)
        if full and full in summary_l:
            return True
        return False
    if s in summary_l:
        return True
    abbrev = _ABBREV_BY_STATE_NAME.get(s)
    if abbrev and re.search(rf"\b{re.escape(abbrev)}\b", summary_l):
        return True
    return False


def _summary_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two summary strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _score_child(draft: FilingIssueDraft, child: EpicChildIssue) -> int:
    """Score a child ticket for matching. Filing unit mismatch returns 0."""
    if child.issue_type_name not in _FILING_CHILD_TYPES:
        return 0
    summary_l = child.summary.lower()

    if draft.filing_unit_code:
        if draft.filing_unit_code.lower() not in summary_l:
            return 0
        score = 4
    else:
        score = 0

    if _state_matches(draft.state, summary_l):
        score += 3

    if draft.filing_period and draft.filing_period.value in ("Q1", "Q2", "Q3", "Q4"):
        period_tok = draft.filing_period.value.lower()
        if period_tok in summary_l:
            score += 2

    if draft.year:
        full_year = draft.year.value
        short_year = full_year[-2:]
        if full_year in summary_l:
            score += 1
        elif short_year in summary_l:
            score += 1

    freq = draft.filing_frequency
    if freq == FilingFrequency.QUARTERLY and "quarter" in summary_l:
        score += 2
    if freq == FilingFrequency.MONTHLY and "month" in summary_l:
        score += 2
    if freq == FilingFrequency.SEMI_MONTHLY and "semi" in summary_l:
        score += 2

    return score


def pick_related_filing_keys(
    draft: FilingIssueDraft,
    children: Sequence[EpicChildIssue],
    *,
    min_score: int = 4,
) -> tuple[list[str], bool]:
    """Return (matched_keys, needs_review).

    - If exactly one best match exists, return it.
    - If multiple candidates tie at the top score, return [] and needs_review=True.
    - If no match meets min_score, return [] and needs_review=True.
    """
    scored: list[tuple[int, str]] = []
    for ch in children:
        s = _score_child(draft, ch)
        if s >= min_score:
            scored.append((s, ch.key))

    if not scored:
        return [], True

    scored.sort(key=lambda t: (-t[0], t[1]))
    best_score = scored[0][0]
    top_matches = [k for sc, k in scored if sc == best_score]

    if len(top_matches) > 1:
        return [], True

    return [scored[0][1]], False


def enrich_draft_with_epic_children(
    draft: FilingIssueDraft,
    children: Sequence[EpicChildIssue],
    *,
    min_score: int = 4,
) -> FilingIssueDraft:
    """Attach related filing keys; copy child due date as primary source of truth."""
    keys, match_needs_review = pick_related_filing_keys(draft, children, min_score=min_score)

    due = draft.due_date
    if len(keys) == 1:
        sole_key = keys[0]
        sole = next((c for c in children if c.key == sole_key), None)
        if sole is not None and sole.duedate:
            due = sole.duedate

    needs_review = draft.needs_mapping_review or match_needs_review

    return draft.model_copy(
        update={
            "related_filing_issue_keys": keys,
            "due_date": due,
            "needs_mapping_review": needs_review,
        }
    )


def jira_issue_link_payload(
    new_issue_key: str,
    related_filing_key: str,
    *,
    link_type_name: str = "Relates",
) -> dict:
    """Build JSON body for ``POST /rest/api/3/issueLink`` (Jira Cloud).

    For the symmetric "Relates" link type, direction is irrelevant — both
    sides show "relates to".  The new issue goes in inwardIssue and the
    existing filing ticket in outwardIssue by convention.
    """
    return {
        "type": {"name": link_type_name},
        "inwardIssue": {"key": new_issue_key},
        "outwardIssue": {"key": related_filing_key},
    }


def filing_frequency_option_id(freq: FilingFrequency | None) -> str | None:
    if freq is None:
        return None
    return FILING_FREQUENCY_IDS.get(freq)
