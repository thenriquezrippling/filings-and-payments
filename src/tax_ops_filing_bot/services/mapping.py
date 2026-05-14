"""Deterministic mapping layer for the FILING Jira project.

Derives issue_type, labels, SLA fields, filing period/year, and parent epic
from metadata extracted by the LLM.  All conventions are based on real tickets
observed in the FILING project (rippling.atlassian.net).

Label convention for blockers: ``Q{quarter}{2-digit-year}-filing-blocker``
  e.g. Q126-filing-blocker, Q226-filing-blocker
Retro items: ``q{quarter}{2-digit-year}-retro-item``
Exclusions: ``q{quarter}{2-digit-year}-exclusions``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from tax_ops_filing_bot.models.filing import (
    FilingFrequency,
    FilingPeriod,
    FilingYear,
    Impact,
    IssueType,
    SLAPriority,
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


def parse_period(raw: str | None) -> tuple[int | None, int | None]:
    """Extract (quarter 1-4, four-digit year) from free-text period string."""
    if not raw:
        return None, None
    m = _QUARTER_RE.search(raw)
    if m:
        q = int(m.group(1) or m.group(3))
        y = int(m.group(2) or m.group(4))
        return q, y
    ym = _YEAR_RE.search(raw)
    if ym:
        return None, int(ym.group(1))
    return None, None


def quarter_to_filing_period(q: int | None) -> FilingPeriod | None:
    return {1: FilingPeriod.Q1, 2: FilingPeriod.Q2,
            3: FilingPeriod.Q3, 4: FilingPeriod.Q4}.get(q)  # type: ignore[arg-type]


def year_to_filing_year(y: int | None) -> FilingYear | None:
    return {2025: FilingYear.Y2025, 2026: FilingYear.Y2026,
            2027: FilingYear.Y2027}.get(y)  # type: ignore[arg-type]


def build_blocker_label(quarter: int | None, year: int | None) -> str | None:
    """Build the period-aware blocker label: Q126-filing-blocker, Q226-filing-blocker, etc."""
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
    """Infer Impact from the LLM hint or description signals."""
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
    """Classify issue type from description content signals."""
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
# SLA inference
# ---------------------------------------------------------------------------

def infer_sla_priority(issue_type: IssueType, impact: Impact | None) -> SLAPriority | None:
    """Default SLA Priority based on issue type and impact."""
    if issue_type != IssueType.BLOCKER:
        return None
    if impact == Impact.ALL_CLIENTS:
        return SLAPriority.P0_CRITICAL
    if impact == Impact.MULTIPLE_CLIENTS:
        return SLAPriority.P1_URGENT
    return SLAPriority.P1_URGENT


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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_mapping(
    *,
    description: str,
    tax_period: str | None = None,
    impact_hint: str | None = None,
) -> MappingResult:
    """Apply deterministic rules to produce Jira-ready fields from extracted metadata."""

    quarter, year = parse_period(tax_period)
    issue_type = classify_issue_type(description)

    filing_period = quarter_to_filing_period(quarter)
    filing_year = year_to_filing_year(year)
    filing_frequency = FilingFrequency.QUARTERLY if quarter else None

    impact = infer_impact(description, impact_hint)
    sla_priority = infer_sla_priority(issue_type, impact)
    sla_tracker = infer_sla_tracker(sla_priority)

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

    return MappingResult(
        issue_type=issue_type,
        labels=sorted(labels),
        filing_period=filing_period,
        year=filing_year,
        filing_frequency=filing_frequency,
        sla_priority=sla_priority,
        sla_tracker=sla_tracker,
        impact=impact,
        parent_epic_key=None,
        needs_mapping_review=needs_review,
    )
