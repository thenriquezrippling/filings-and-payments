"""Pydantic models for FILING Jira issue drafts.

Field names, allowed values, and Jira IDs are sourced from the live FILING
project (key FILING, id 17112) on rippling.atlassian.net.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums matching actual FILING project configuration
# ---------------------------------------------------------------------------

class IssueType(str, Enum):
    """Issue types that exist in the FILING project (non-subtask, non-epic)."""

    BLOCKER = "Blocker"                  # id 20302
    FILING_EXCEPTION = "Filing Exception"  # id 24564
    FEATURE_REQUEST = "Feature Request"  # id 20303
    QUARTERLY = "Quarterly"              # id 20087
    MONTHLY = "Monthly"                  # id 20086
    SEMI_MONTHLY = "Semi-Monthly"        # id 23370
    ANNUAL_REC = "Annual Rec"            # id 20088
    W2 = "W-2"                           # id 20122
    FORM_1099 = "1099"                   # id 18506
    RETRO = "Retro"                      # id 20418
    EXECUTIVE_SUMMARY = "Executive Summary"  # id 20499
    PR_W2_W2C = "PR W-2/W-2C"           # id 23298


ISSUE_TYPE_JIRA_IDS: dict[IssueType, str] = {
    IssueType.BLOCKER: "20302",
    IssueType.FILING_EXCEPTION: "24564",
    IssueType.FEATURE_REQUEST: "20303",
    IssueType.QUARTERLY: "20087",
    IssueType.MONTHLY: "20086",
    IssueType.SEMI_MONTHLY: "23370",
    IssueType.ANNUAL_REC: "20088",
    IssueType.W2: "20122",
    IssueType.FORM_1099: "18506",
    IssueType.RETRO: "20418",
    IssueType.EXECUTIVE_SUMMARY: "20499",
    IssueType.PR_W2_W2C: "23298",
}


class SLAPriority(str, Enum):
    """customfield_21648 — required for Blocker."""

    P0_CRITICAL = "P0 - Critical"    # id 32739
    P1_URGENT = "P1 - Urgent"        # id 32740
    P2_HIGH = "P2 - High"            # id 32741
    P3_MEDIUM = "P3 - Medium"        # id 32742
    RETRO = "Retro"                  # id 32743


SLA_PRIORITY_IDS: dict[SLAPriority, str] = {
    SLAPriority.P0_CRITICAL: "32739",
    SLAPriority.P1_URGENT: "32740",
    SLAPriority.P2_HIGH: "32741",
    SLAPriority.P3_MEDIUM: "32742",
    SLAPriority.RETRO: "32743",
}


class SLATracker(str, Enum):
    """customfield_21649 — required for Blocker."""

    SAME_DAY = "Same-Day Resolution"     # id 32744
    ONE_DAY = "1-Day Resolution"         # id 32745
    TWO_DAY = "2-Day Resolution"         # id 32746
    THREE_DAY = "3-Day Resolution"       # id 32747
    FOR_RETRO = "For Retro"              # id 32748
    WATCH_ITEM = "Watch Item"            # id 39616


SLA_TRACKER_IDS: dict[SLATracker, str] = {
    SLATracker.SAME_DAY: "32744",
    SLATracker.ONE_DAY: "32745",
    SLATracker.TWO_DAY: "32746",
    SLATracker.THREE_DAY: "32747",
    SLATracker.FOR_RETRO: "32748",
    SLATracker.WATCH_ITEM: "39616",
}


class FilingPeriod(str, Enum):
    """customfield_21646 — required for Blocker, optional for others."""

    Q1 = "Q1"          # id 32729
    Q2 = "Q2"          # id 32730
    Q3 = "Q3"          # id 32731
    Q4 = "Q4"          # id 32732
    ANNUALS = "Annuals"  # id 32733
    W2 = "W-2"          # id 32734
    FORM_1099 = "1099"  # id 32735


FILING_PERIOD_IDS: dict[FilingPeriod, str] = {
    FilingPeriod.Q1: "32729",
    FilingPeriod.Q2: "32730",
    FilingPeriod.Q3: "32731",
    FilingPeriod.Q4: "32732",
    FilingPeriod.ANNUALS: "32733",
    FilingPeriod.W2: "32734",
    FilingPeriod.FORM_1099: "32735",
}


class FilingYear(str, Enum):
    """customfield_21647 — required for Blocker."""

    Y2025 = "2025"  # id 32736
    Y2026 = "2026"  # id 32737
    Y2027 = "2027"  # id 32738


FILING_YEAR_IDS: dict[FilingYear, str] = {
    FilingYear.Y2025: "32736",
    FilingYear.Y2026: "32737",
    FilingYear.Y2027: "32738",
}


class FilingFrequency(str, Enum):
    """customfield_21650 — required for Blocker."""

    ANNUAL = "Annual"          # id 32749
    MONTHLY = "Monthly"        # id 32895
    QUARTERLY = "Quarterly"    # id 32896
    SEMI_MONTHLY = "Semi-Monthly"  # id 32897


FILING_FREQUENCY_IDS: dict[FilingFrequency, str] = {
    FilingFrequency.ANNUAL: "32749",
    FilingFrequency.MONTHLY: "32895",
    FilingFrequency.QUARTERLY: "32896",
    FilingFrequency.SEMI_MONTHLY: "32897",
}


class Impact(str, Enum):
    """customfield_27156 — required for Blocker."""

    ALL_CLIENTS = "All Clients"          # id 40336
    MULTIPLE_CLIENTS = "Multiple Clients"  # id 40337
    SINGLE_CLIENT = "Single Client"      # id 40338


IMPACT_IDS: dict[Impact, str] = {
    Impact.ALL_CLIENTS: "40336",
    Impact.MULTIPLE_CLIENTS: "40337",
    Impact.SINGLE_CLIENT: "40338",
}


# ---------------------------------------------------------------------------
# Thread and LLM extraction models
# ---------------------------------------------------------------------------

class ThreadMessage(BaseModel):
    """A single message from a Slack thread."""

    author: str
    timestamp: str
    text: str
    is_bot: bool = False


class LLMExtraction(BaseModel):
    """Raw output from the LLM — only fields the LLM is responsible for."""

    summary: str = Field(
        ...,
        description="Concise one-line summary for the Jira issue title",
        max_length=255,
    )
    description: str = Field(
        ...,
        description="Operational issue description with filing context only",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="LLM confidence in the extraction (0.0–1.0)",
    )
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Tax jurisdiction (state abbreviation or city name)",
    )
    state: Optional[str] = Field(
        default=None,
        description="Two-letter state abbreviation (e.g. PA, NY, TX)",
    )
    tax_type: Optional[str] = Field(
        default=None,
        description="Tax type (e.g. EIT, LST, SUI, SWT)",
    )
    tax_period: Optional[str] = Field(
        default=None,
        description="Tax period (e.g. 1Q2026, Q1 2026, April 2026)",
    )
    agency: Optional[str] = Field(
        default=None,
        description="Agency name if identifiable",
    )
    filing_code: Optional[str] = Field(
        default=None,
        description="Filing code identifier (e.g. PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE)",
    )
    ff_client_id: Optional[str] = Field(
        default=None,
        description="FF Client ID(s) if mentioned (free text, may be comma-separated)",
    )
    client_or_entity: Optional[str] = Field(
        default=None,
        description="Client or entity name if mentioned",
    )
    reporter: Optional[str] = Field(
        default=None,
        description="Slack user who initiated the thread",
    )
    impact_scope: Optional[str] = Field(
        default=None,
        description="Impact hint: 'all clients', 'multiple clients', 'single client', or null",
    )


# ---------------------------------------------------------------------------
# Final draft model — matches FILING project Jira schema
# ---------------------------------------------------------------------------

class FilingIssueDraft(BaseModel):
    """Structured draft for a FILING Jira issue, after deterministic mapping.

    Fields map to actual Jira project FILING (id 17112) on rippling.atlassian.net.
    """

    # Standard Jira fields
    summary: str = Field(
        ...,
        description="Jira summary (required)",
        max_length=255,
    )
    description: str = Field(
        ...,
        description="Jira description — operational content only",
    )
    issue_type: IssueType = Field(
        default=IssueType.BLOCKER,
        description="FILING issue type",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Jira labels following FILING conventions (e.g. Q126-filing-blocker)",
    )
    parent_epic_key: Optional[str] = Field(
        default=None,
        description="Parent Epic key (e.g. FILING-2589 for Pennsylvania)",
    )

    # Required custom fields for Blocker
    filing_period: Optional[FilingPeriod] = Field(
        default=None,
        description="customfield_21646 — Filing / Period",
    )
    year: Optional[FilingYear] = Field(
        default=None,
        description="customfield_21647 — Year",
    )
    sla_priority: Optional[SLAPriority] = Field(
        default=None,
        description="customfield_21648 — SLA Priority",
    )
    sla_tracker: Optional[SLATracker] = Field(
        default=None,
        description="customfield_21649 — SLA Tracker",
    )
    filing_frequency: Optional[FilingFrequency] = Field(
        default=None,
        description="customfield_21650 — Filing Frequency",
    )
    ff_client_id: Optional[str] = Field(
        default=None,
        description="customfield_25274 — FF Client ID",
    )
    impact: Optional[Impact] = Field(
        default=None,
        description="customfield_27156 — Impact scope",
    )

    # Optional custom fields
    issue_agency_type: Optional[str] = Field(
        default=None,
        description="customfield_21075 — Issue/Agency Type (free text)",
    )
    state: Optional[str] = Field(
        default=None,
        description="customfield_21080 — State abbreviation",
    )
    filing_unit_code: Optional[str] = Field(
        default=None,
        description="customfield_21471 — Filing Unit Code",
    )
    company_name: Optional[str] = Field(
        default=None,
        description="customfield_25275 — Company Name",
    )

    # Metadata (not sent to Jira, used for bot workflow)
    source_channel: Optional[str] = Field(default=None)
    source_thread_ts: Optional[str] = Field(default=None)
    reporter: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_mapping_review: bool = Field(
        default=False,
        description="True when no deterministic mapping exists",
    )
