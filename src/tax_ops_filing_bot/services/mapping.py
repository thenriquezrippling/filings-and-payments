"""Deterministic mapping layer for the FILING Jira project.

Derives issue_type, labels, SLA fields, filing period/year, and parent epic
from metadata extracted by the LLM.  All conventions are based on real tickets
observed in the FILING project (rippling.atlassian.net).

IMPORTANT: Jira's default Priority field is NOT used.  All SLA information
goes through SLA Priority, SLA Tracker, and SLA Status custom fields.

SLA rules by Work Type:
  Blocker   → SLA Priority from due-date proximity, SLA Tracker mapped,
              SLA Status = At Risk when past-due or P0, else On Track
  Retro     → SLA Priority=Retro, SLA Tracker=For Retro, SLA Status=On Track
  Others    → SLA Priority/Tracker/Status left blank

Label convention for blockers: ``Q{quarter}{2-digit-year}-filing-blocker``
Retro items: ``q{quarter}{2-digit-year}-retro-item``
Exclusions: ``q{quarter}{2-digit-year}-exclusions``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from tax_ops_filing_bot.models.filing import (
    FilingFrequency,
    FilingPeriod,
    FilingYear,
    Impact,
    IssueType,
    SLAPriority,
    SLAStatus,
    SLATracker,
)


@dataclass(frozen=True)
class MappingResult:
    """Output of the deterministic mapping layer."""

    issue_type: IssueType
    labels: list[str] = field(default_factory=list)
    filing_period: Optional[FilingPeriod] = None
    year: Optional[FilingYear] = None
    filing_frequency: Optional[FilingFrequency] = None
    sla_priority: Optional[SLAPriority] = None
    sla_tracker: Optional[SLATracker] = None
    sla_status: Optional[SLAStatus] = None
    impact: Optional[Impact] = None
    parent_epic_key: Optional[str] = None
    needs_mapping_review: bool = False


# ---------------------------------------------------------------------------
# Period parsing
# ---------------------------------------------------------------------------

_QUARTER_RE = re.compile(
    r"(?:(\d)[Qq]\s*(\d{4}))|(?:[Qq](\d)\s*(\d{4}))", re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(202[4-9])\b")
_MONTH_RE = re.compile(
    r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|"
    r"july|jul|august|aug|september|sep|sept|october|oct|november|nov|"
    r"december|dec)\s+(\d{4})\b",
    re.IGNORECASE,
)
_MMYYYY_RE = re.compile(r"\b(0?[1-9]|1[0-2])[/-](\d{4})\b")


_MONTH_NAME_TO_NUM: dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _parse_month_year(raw: str) -> tuple[int | None, int | None]:
    m = _MONTH_RE.search(raw)
    if m:
        month = _MONTH_NAME_TO_NUM[m.group(1).lower()]
        return month, int(m.group(2))
    m2 = _MMYYYY_RE.search(raw)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    return None, None


def parse_period_meta(raw: str | None) -> tuple[int | None, int | None, bool]:
    """Return (quarter 1-4 or inferred, year, explicit_quarter).

    ``explicit_quarter`` is True when the text names a quarter (1Q2026, Q2 2026).
    When a calendar month is used (April 2026), quarter is the fiscal calendar
    quarter (1–4) for Jira Filing / Period alignment and ``explicit_quarter`` is
    False so filing frequency can be set to Monthly.
    """
    if not raw:
        return None, None, False
    m = _QUARTER_RE.search(raw)
    if m:
        q = int(m.group(1) or m.group(3))
        y = int(m.group(2) or m.group(4))
        return q, y, True
    month, y = _parse_month_year(raw)
    if month is not None and y is not None:
        q = (month - 1) // 3 + 1
        return q, y, False
    ym = _YEAR_RE.search(raw)
    if ym:
        return None, int(ym.group(1)), False
    return None, None, False


def parse_period(raw: str | None) -> tuple[int | None, int | None]:
    """Extract (quarter 1-4 or calendar-inferred quarter, four-digit year)."""
    q, y, _ = parse_period_meta(raw)
    return q, y


def quarter_to_filing_period(q: int | None) -> FilingPeriod | None:
    return {1: FilingPeriod.Q1, 2: FilingPeriod.Q2,
            3: FilingPeriod.Q3, 4: FilingPeriod.Q4}.get(q)  # type: ignore[arg-type]


def year_to_filing_year(y: int | None) -> FilingYear | None:
    return {2025: FilingYear.Y2025, 2026: FilingYear.Y2026,
            2027: FilingYear.Y2027}.get(y)  # type: ignore[arg-type]


def build_blocker_label(quarter: int | None, year: int | None) -> str | None:
    if quarter is None or year is None:
        return None
    short_year = year % 100
    return f"Q{quarter}{short_year}-filing-blocker"


def build_retro_label(quarter: int | None, year: int | None) -> str | None:
    if quarter is None or year is None:
        return None
    short_year = year % 100
    return f"q{quarter}{short_year}-retro-item"


# ---------------------------------------------------------------------------
# Impact inference
# ---------------------------------------------------------------------------

def infer_impact(description: str, impact_hint: str | None) -> Impact | None:
    if impact_hint:
        hint_lower = impact_hint.lower().strip()
        if "all" in hint_lower:
            return Impact.ALL_CLIENTS
        if "multiple" in hint_lower:
            return Impact.MULTIPLE_CLIENTS
        if "single" in hint_lower:
            return Impact.SINGLE_CLIENT

    desc_lower = description.lower()
    if re.search(r"all\s+clients?\s+(are\s+)?show", desc_lower):
        return Impact.ALL_CLIENTS
    if re.search(r"multiple\s+clients?", desc_lower):
        return Impact.MULTIPLE_CLIENTS
    return None


# ---------------------------------------------------------------------------
# Issue type classification
# ---------------------------------------------------------------------------

def classify_issue_type(description: str) -> IssueType:
    desc_lower = description.lower()

    blocker_signals = [
        r"incorrect\s+(form|tax\s+year|amount|data)",
        r"wrong\s+(year|period|form|amount)",
        r"mismatch",
        r"showing\s+.{0,30}\s+instead\s+of",
        r"needs?\s+to\s+be\s+changed",
        r"may\s+need\s+to\s+be\s+changed",
        r"missing\s+(account|id|number|ssn|ee|employee)",
        r"reject",
        r"cannot\s+(safely\s+)?proceed",
        r"deadline",
        r"peo.*company\s+name",
        r"et-\d{4}",
        r"form\s+(output|generation|display)",
        r"all\s+clients?\s+(are\s+)?show",
        r"negative\s+(taxable\s+)?wages",
        r"file\s+(regeneration|error)",
        r"\$0\s*filing",
        r"wage\s+discrepanc",
    ]
    for sig in blocker_signals:
        if re.search(sig, desc_lower):
            return IssueType.BLOCKER

    exception_signals = [
        r"after\s+submission",
        r"amendment",
        r"follow.?up",
        r"already\s+(filed|submitted)",
        r"filing\s+exception",
        r"exclusion",
    ]
    for sig in exception_signals:
        if re.search(sig, desc_lower):
            return IssueType.FILING_EXCEPTION

    feature_signals = [
        r"enhancement",
        r"feature\s+request",
        r"nice\s+to\s+have",
        r"non.?urgent",
    ]
    for sig in feature_signals:
        if re.search(sig, desc_lower):
            return IssueType.FEATURE_REQUEST

    return IssueType.BLOCKER


# ---------------------------------------------------------------------------
# SLA inference — based on due-date proximity only, NOT impact
# ---------------------------------------------------------------------------

def compute_blocker_sla(
    due_date: date | None,
    today: date,
) -> tuple[SLAPriority | None, SLATracker | None, SLAStatus | None]:
    """Compute SLA fields for a Blocker based purely on due-date proximity.

    Rules:
      ≤ 3 days or past due → P0 Critical / Same-Day / At Risk
      ≤ 5 days             → P1 Urgent  / 1-Day   / On Track
      ≤ 10 days            → P2 High    / 2-Day   / On Track
      > 10 days            → P3 Medium  / 3-Day   / On Track
      no due date          → None / None / None (needs_mapping_review)
    """
    if due_date is None:
        return None, None, None

    days_until = (due_date - today).days

    if days_until <= 3:
        priority = SLAPriority.P0_CRITICAL
        tracker = SLATracker.SAME_DAY
        status = SLAStatus.AT_RISK
    elif days_until <= 5:
        priority = SLAPriority.P1_URGENT
        tracker = SLATracker.ONE_DAY
        status = SLAStatus.AT_RISK if days_until < 0 else SLAStatus.ON_TRACK
    elif days_until <= 10:
        priority = SLAPriority.P2_HIGH
        tracker = SLATracker.TWO_DAY
        status = SLAStatus.ON_TRACK
    else:
        priority = SLAPriority.P3_MEDIUM
        tracker = SLATracker.THREE_DAY
        status = SLAStatus.ON_TRACK

    if days_until < 0:
        status = SLAStatus.AT_RISK

    return priority, tracker, status


def compute_retro_sla() -> tuple[SLAPriority, SLATracker, SLAStatus]:
    """Retro always gets fixed SLA values."""
    return SLAPriority.RETRO, SLATracker.FOR_RETRO, SLAStatus.ON_TRACK


def infer_sla_tracker(sla_priority: SLAPriority | None) -> SLATracker | None:
    if sla_priority is None:
        return None
    return {
        SLAPriority.P0_CRITICAL: SLATracker.SAME_DAY,
        SLAPriority.P1_URGENT: SLATracker.ONE_DAY,
        SLAPriority.P2_HIGH: SLATracker.TWO_DAY,
        SLAPriority.P3_MEDIUM: SLATracker.THREE_DAY,
        SLAPriority.RETRO: SLATracker.FOR_RETRO,
    }.get(sla_priority)


def infer_filing_frequency(
    quarter: int | None,
    explicit_quarter: bool,
) -> FilingFrequency | None:
    if quarter is None:
        return None
    if explicit_quarter:
        return FilingFrequency.QUARTERLY
    return FilingFrequency.MONTHLY


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_mapping(
    *,
    description: str,
    tax_period: str | None = None,
    impact_hint: str | None = None,
    due_date: date | None = None,
    today: date | None = None,
) -> MappingResult:
    """Apply deterministic rules to produce Jira-ready fields from extracted metadata.

    SLA fields depend ONLY on Work Type and due-date proximity, never on impact.
    Impact is recorded as context but does not influence SLA Priority.
    """
    today_eff = today or date.today()

    quarter, year, explicit_quarter = parse_period_meta(tax_period)
    issue_type = classify_issue_type(description)

    filing_period = quarter_to_filing_period(quarter)
    filing_year = year_to_filing_year(year)
    filing_frequency = infer_filing_frequency(quarter, explicit_quarter)

    impact = infer_impact(description, impact_hint)

    sla_priority: SLAPriority | None = None
    sla_tracker: SLATracker | None = None
    sla_status: SLAStatus | None = None

    if issue_type == IssueType.BLOCKER:
        sla_priority, sla_tracker, sla_status = compute_blocker_sla(due_date, today_eff)
    elif issue_type == IssueType.RETRO:
        sla_priority, sla_tracker, sla_status = compute_retro_sla()

    labels: list[str] = []
    if issue_type == IssueType.BLOCKER:
        blocker_label = build_blocker_label(quarter, year)
        if blocker_label:
            labels.append(blocker_label)
    elif issue_type == IssueType.FILING_EXCEPTION:
        exclusion_label = (
            f"q{quarter}{year % 100}-exclusions"
            if quarter and year else None
        )
        if exclusion_label:
            labels.append(exclusion_label)

    needs_review = filing_period is None or filing_year is None
    if issue_type == IssueType.BLOCKER and due_date is None:
        needs_review = True

    return MappingResult(
        issue_type=issue_type,
        labels=sorted(labels),
        filing_period=filing_period,
        year=filing_year,
        filing_frequency=filing_frequency,
        sla_priority=sla_priority,
        sla_tracker=sla_tracker,
        sla_status=sla_status,
        impact=impact,
        parent_epic_key=None,
        needs_mapping_review=needs_review,
    )
