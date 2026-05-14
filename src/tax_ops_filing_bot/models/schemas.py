"""Pydantic schemas for structured LLM output and service data transfer."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FilingIssueCategory(str, Enum):
    """Issue categories derived from recurring filing-season themes."""

    MISSING_EMPLOYEE_DATA = "missing_employee_data"
    INCORRECT_WAGES = "incorrect_wages"
    PEO_RECONCILIATION = "peo_reconciliation"
    ACCOUNT_SYNC = "account_sync"
    PAYMENT_ISSUE = "payment_issue"
    EFILE_BLOCKED = "efile_blocked"
    AGENCY_CHANGE = "agency_change"
    TAX_CONFIG = "tax_config"
    OTHER = "other"


class AgencyCode(str, Enum):
    """Frequently-referenced agency codes from the filing channel."""

    IRS941 = "IRS941"
    NVSUI = "NVSUI"
    FLSUI = "FLSUI"
    MESW = "MESW"
    NJSWSUI = "NJSWSUI"
    WASUI = "WASUI"
    MISUI = "MISUI"
    ILSUI = "ILSUI"
    OKSUI = "OKSUI"
    PASUI = "PASUI"
    MDSUI = "MDSUI"
    MAPFML = "MAPFML"
    TNSUI = "TNSUI"
    CAEDD = "CAEDD"
    DCSUI = "DCSUI"
    WISUI = "WISUI"
    ORFILE = "ORFILE"
    VASUI = "VASUI"
    MOSUI = "MOSUI"
    NYSWSUI = "NYSWSUI"
    MNSUI = "MNSUI"
    MNPFML = "MNPFML"
    WAWC = "WAWC"
    WYSUI = "WYSUI"
    NMWCFILE = "NMWCFILE"
    NYMCTMT = "NYMCTMT"
    SDSUI = "SDSUI"
    OTHER = "OTHER"


class ThreadMessage(BaseModel):
    """A single Slack message within a thread."""

    user: str = Field(description="Slack user ID of the author")
    text: str = Field(description="Raw message text")
    ts: str = Field(description="Slack message timestamp (unique ID)")


class ThreadContext(BaseModel):
    """Slack thread context passed to the LLM for issue extraction."""

    channel_id: str
    thread_ts: str
    messages: list[ThreadMessage] = Field(min_length=1)
    permalink: Optional[str] = None

    @property
    def reply_count(self) -> int:
        return len(self.messages) - 1


class FilingIssueDraft(BaseModel):
    """Structured output the LLM produces from a Slack thread.

    Maps directly to Jira issue fields for project FILING.
    """

    summary: str = Field(
        max_length=255,
        description="Jira issue summary / title",
    )
    description: str = Field(
        description="Markdown description for the Jira issue body",
    )
    category: FilingIssueCategory = Field(
        description="Primary issue category",
    )
    agency: Optional[AgencyCode] = Field(
        default=None,
        description="Affected agency code, if identifiable",
    )
    priority: str = Field(
        default="P1",
        pattern=r"^P[0-4]$",
        description="Priority level P0–P4",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Jira labels to apply (e.g. ['q1-2026', 'peo'])",
    )
    affected_entity_ids: list[str] = Field(
        default_factory=list,
        description="Rippling entity / FFID identifiers mentioned in the thread",
    )
    suggested_dri: Optional[str] = Field(
        default=None,
        description="Suggested DRI (person name or Slack handle) inferred from context",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="LLM confidence in the extraction (0.0–1.0)",
    )


class SyncRequest(BaseModel):
    """Request to sync a Slack thread to an existing Jira issue."""

    issue_key: str = Field(
        pattern=r"^[A-Z]+-\d+$",
        description="Jira issue key, e.g. FILING-5911",
    )
    thread: ThreadContext
    append_only: bool = Field(
        default=True,
        description="If True, only append new messages as a comment",
    )
