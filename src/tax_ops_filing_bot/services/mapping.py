"""Deterministic mapping layer for agency/jurisdiction/tax_type to Jira fields.

The LLM extracts raw metadata; this module applies rule-based mappings to
assign issue_type, priority, parent_epic_key, and standardized labels.
If no mapping exists, needs_mapping_review is set to True.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from tax_ops_filing_bot.models.filing import IssuePriority, IssueType


@dataclass(frozen=True)
class MappingResult:
    """Output of the deterministic mapping layer."""

    issue_type: IssueType
    priority: IssuePriority
    parent_epic_key: Optional[str]
    labels: list[str] = field(default_factory=list)
    needs_mapping_review: bool = False


@dataclass(frozen=True)
class AgencyMapping:
    """Mapping rule for a single agency/jurisdiction/tax_type combination."""

    jurisdiction_pattern: re.Pattern[str]
    tax_type_pattern: re.Pattern[str]
    state_label: str
    jurisdiction_label: str
    tax_type_label: str
    parent_epic_key: str
    issue_category_labels: list[str] = field(default_factory=list)


AGENCY_MAPPINGS: list[AgencyMapping] = [
    AgencyMapping(
        jurisdiction_pattern=re.compile(r"pittsburgh", re.IGNORECASE),
        tax_type_pattern=re.compile(r"EIT|earned\s+income", re.IGNORECASE),
        state_label="pa-local",
        jurisdiction_label="pittsburgh",
        tax_type_label="eit",
        parent_epic_key="FILING-101",
        issue_category_labels=["payroll-expense-tax"],
    ),
    AgencyMapping(
        jurisdiction_pattern=re.compile(r"pittsburgh", re.IGNORECASE),
        tax_type_pattern=re.compile(r"LST|local\s+services", re.IGNORECASE),
        state_label="pa-local",
        jurisdiction_label="pittsburgh",
        tax_type_label="lst",
        parent_epic_key="FILING-101",
    ),
    AgencyMapping(
        jurisdiction_pattern=re.compile(r"philadelphia", re.IGNORECASE),
        tax_type_pattern=re.compile(r"BIRT|business\s+income", re.IGNORECASE),
        state_label="pa-local",
        jurisdiction_label="philadelphia",
        tax_type_label="birt",
        parent_epic_key="FILING-102",
    ),
    AgencyMapping(
        jurisdiction_pattern=re.compile(r"philadelphia", re.IGNORECASE),
        tax_type_pattern=re.compile(r"EIT|earned\s+income|wage", re.IGNORECASE),
        state_label="pa-local",
        jurisdiction_label="philadelphia",
        tax_type_label="eit",
        parent_epic_key="FILING-102",
    ),
    AgencyMapping(
        jurisdiction_pattern=re.compile(r"california|CA\b", re.IGNORECASE),
        tax_type_pattern=re.compile(r"SUI|state\s+unemployment", re.IGNORECASE),
        state_label="ca-state",
        jurisdiction_label="california",
        tax_type_label="sui",
        parent_epic_key="FILING-200",
    ),
    AgencyMapping(
        jurisdiction_pattern=re.compile(r"new\s*york|NYC|NY\b", re.IGNORECASE),
        tax_type_pattern=re.compile(r"PIT|personal\s+income", re.IGNORECASE),
        state_label="ny-state",
        jurisdiction_label="new-york",
        tax_type_label="pit",
        parent_epic_key="FILING-300",
    ),
]

FILING_CODE_PATTERNS: dict[re.Pattern[str], dict[str, str]] = {
    re.compile(r"PALOCALTREASURER.*PITTSBURGH.*PAYEXP", re.IGNORECASE): {
        "jurisdiction": "City of Pittsburgh",
        "tax_type": "EIT",
        "agency": "PA Local Treasurer - City of Pittsburgh",
    },
    re.compile(r"PALOCALTREASURER.*PITTSBURGH.*LST", re.IGNORECASE): {
        "jurisdiction": "City of Pittsburgh",
        "tax_type": "LST",
        "agency": "PA Local Treasurer - City of Pittsburgh",
    },
    re.compile(r"PHILA.*BIRT", re.IGNORECASE): {
        "jurisdiction": "City of Philadelphia",
        "tax_type": "BIRT",
        "agency": "City of Philadelphia Revenue",
    },
}


def _classify_issue_type(
    *,
    tax_type: str | None,
    jurisdiction: str | None,
    description: str,
) -> IssueType:
    """Classify issue type based on content signals.

    Blocker is checked first because incorrect form output, data mismatches,
    and wrong tax years block filing even when they affect multiple clients.
    Incident is reserved for explicitly systemic / production-wide failures
    that go beyond a single form or filing code issue.
    """
    desc_lower = description.lower()

    blocker_signals = [
        r"incorrect\s+(form|tax\s+year|amount|data)",
        r"wrong\s+(year|period|form|amount)",
        r"mismatch",
        r"showing\s+.{0,30}\s+instead\s+of",
        r"needs?\s+to\s+be\s+changed",
        r"may\s+need\s+to\s+be\s+changed",
        r"missing\s+(account|id|number)",
        r"reject",
        r"cannot\s+(safely\s+)?proceed",
        r"deadline",
        r"peo.*company\s+name",
        r"et-\d{4}",
        r"form\s+(output|generation|display)",
        r"all\s+clients?\s+(are\s+)?show",
    ]
    for sig in blocker_signals:
        if re.search(sig, desc_lower):
            return IssueType.BLOCKER

    incident_signals = [
        r"multi.?client\s+(production\s+)?fail",
        r"systemic\s+(failure|issue|outage|error)",
        r"production\s+(failure|outage|incident)",
        r"widespread\s+(failure|outage|issue)",
        r"platform.wide",
        r"all\s+(filings?|payments?)\s+(fail|reject|error)",
    ]
    for sig in incident_signals:
        if re.search(sig, desc_lower):
            return IssueType.INCIDENT

    exception_signals = [
        r"after\s+submission",
        r"amendment",
        r"follow.?up",
        r"already\s+(filed|submitted)",
    ]
    for sig in exception_signals:
        if re.search(sig, desc_lower):
            return IssueType.FILING_EXCEPTION

    improvement_signals = [
        r"\bsop\b",
        r"workflow\s+(enhancement|improvement)",
        r"operational\s+process",
    ]
    for sig in improvement_signals:
        if re.search(sig, desc_lower):
            return IssueType.PROCESS_IMPROVEMENT

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


def _classify_priority(issue_type: IssueType) -> IssuePriority:
    """Derive priority from issue type."""
    return {
        IssueType.BLOCKER: IssuePriority.HIGHEST,
        IssueType.INCIDENT: IssuePriority.HIGHEST,
        IssueType.FILING_EXCEPTION: IssuePriority.HIGH,
        IssueType.FEATURE_REQUEST: IssuePriority.LOW,
        IssueType.PROCESS_IMPROVEMENT: IssuePriority.LOW,
    }[issue_type]


def _normalize_period_label(period: str | None) -> str | None:
    """Normalize tax period to label format: 1Q2026 -> q1-2026."""
    if not period:
        return None
    m = re.match(r"(\d)Q\s*(\d{4})", period, re.IGNORECASE)
    if m:
        return f"q{m.group(1)}-{m.group(2)}"
    m = re.match(r"Q(\d)\s*(\d{4})", period, re.IGNORECASE)
    if m:
        return f"q{m.group(1)}-{m.group(2)}"
    m = re.match(r"FY\s*(\d{4})", period, re.IGNORECASE)
    if m:
        return f"fy-{m.group(1)}"
    m = re.match(r"(\d{4})", period)
    if m:
        return m.group(1)
    return period.lower().replace(" ", "-")


def resolve_filing_code(code: str) -> dict[str, str] | None:
    """Try to resolve a filing code string to agency metadata."""
    for pattern, metadata in FILING_CODE_PATTERNS.items():
        if pattern.search(code):
            return metadata
    return None


def apply_mapping(
    *,
    jurisdiction: str | None,
    tax_type: str | None,
    tax_period: str | None,
    agency: str | None,
    filing_code: str | None,
    description: str,
) -> MappingResult:
    """Apply deterministic rules to produce issue_type, priority, epic, labels."""
    if filing_code:
        resolved = resolve_filing_code(filing_code)
        if resolved:
            jurisdiction = jurisdiction or resolved.get("jurisdiction")
            tax_type = tax_type or resolved.get("tax_type")
            agency = agency or resolved.get("agency")

    for mapping in AGENCY_MAPPINGS:
        j_match = jurisdiction and mapping.jurisdiction_pattern.search(jurisdiction)
        t_match = tax_type and mapping.tax_type_pattern.search(tax_type)
        if j_match and t_match:
            issue_type = _classify_issue_type(
                tax_type=tax_type,
                jurisdiction=jurisdiction,
                description=description,
            )
            priority = _classify_priority(issue_type)

            labels = [
                mapping.jurisdiction_label,
                mapping.state_label,
                mapping.tax_type_label,
            ]
            labels.extend(mapping.issue_category_labels)

            period_label = _normalize_period_label(tax_period)
            if period_label:
                labels.append(period_label)

            if issue_type == IssueType.BLOCKER:
                labels.append("filing-blocker")
            elif issue_type == IssueType.INCIDENT:
                labels.append("incident")

            desc_lower = description.lower()
            if re.search(r"form\s+(output|generation|display|showing)", desc_lower):
                labels.append("form-output")
            if re.search(r"peo|professional\s+employer", desc_lower):
                labels.append("form-output")

            return MappingResult(
                issue_type=issue_type,
                priority=priority,
                parent_epic_key=mapping.parent_epic_key,
                labels=sorted(set(labels)),
            )

    issue_type = _classify_issue_type(
        tax_type=tax_type,
        jurisdiction=jurisdiction,
        description=description,
    )
    priority = _classify_priority(issue_type)

    labels: list[str] = []
    if jurisdiction:
        labels.append(jurisdiction.lower().replace(" ", "-").replace(".", ""))
    if tax_type:
        labels.append(tax_type.lower())
    period_label = _normalize_period_label(tax_period)
    if period_label:
        labels.append(period_label)
    if issue_type == IssueType.BLOCKER:
        labels.append("filing-blocker")
    elif issue_type == IssueType.INCIDENT:
        labels.append("incident")

    return MappingResult(
        issue_type=issue_type,
        priority=priority,
        parent_epic_key=None,
        labels=sorted(set(labels)),
        needs_mapping_review=True,
    )
