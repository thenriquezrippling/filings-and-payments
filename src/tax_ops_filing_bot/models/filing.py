"""Pydantic models for FILING Jira issue drafts."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IssuePriority(str, Enum):
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    LOWEST = "Lowest"


class IssueType(str, Enum):
    BLOCKER = "Blocker"
    FILING_EXCEPTION = "Filing Exception"
    INCIDENT = "Incident"
    FEATURE_REQUEST = "Feature Request"
    PROCESS_IMPROVEMENT = "Process Improvement"


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
        description="Tax jurisdiction (city, state, county) if identifiable",
    )
    tax_type: Optional[str] = Field(
        default=None,
        description="Tax type (e.g. EIT, LST, BIRT, payroll-expense)",
    )
    tax_period: Optional[str] = Field(
        default=None,
        description="Tax period or year if mentioned (e.g. 1Q2026, 2025)",
    )
    agency: Optional[str] = Field(
        default=None,
        description="Agency name or filing code prefix if identifiable",
    )
    filing_code: Optional[str] = Field(
        default=None,
        description="Filing code if identifiable (e.g. PALOCALTREASURERCITYOFPITTSBURGHPAYEXPFILE)",
    )
    client_or_entity: Optional[str] = Field(
        default=None,
        description="Client or entity name if mentioned",
    )
    reporter: Optional[str] = Field(
        default=None,
        description="Slack user who initiated the thread",
    )


class FilingIssueDraft(BaseModel):
    """Structured draft for a FILING Jira issue, after deterministic mapping."""

    summary: str = Field(
        ...,
        description="Concise one-line summary for the Jira issue title",
        max_length=255,
    )
    description: str = Field(
        ...,
        description="Full issue description — operational content only, no implementation notes",
    )
    issue_type: IssueType = Field(
        default=IssueType.BLOCKER,
        description="Tax Ops issue type",
    )
    priority: IssuePriority = Field(
        default=IssuePriority.MEDIUM,
        description="Issue priority",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Standardized labels from deterministic mapping",
    )
    parent_epic_key: Optional[str] = Field(
        default=None,
        description="FILING epic key from mapping layer (e.g. FILING-100)",
    )
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Tax jurisdiction (city, state, county) if identifiable",
    )
    tax_type: Optional[str] = Field(
        default=None,
        description="Tax type (e.g. EIT, LST, BIRT, payroll-expense)",
    )
    tax_period: Optional[str] = Field(
        default=None,
        description="Tax period or year if mentioned (e.g. 1Q2026, 2025)",
    )
    agency: Optional[str] = Field(
        default=None,
        description="Filing agency",
    )
    filing_code: Optional[str] = Field(
        default=None,
        description="Filing code identifier",
    )
    client_or_entity: Optional[str] = Field(
        default=None,
        description="Client or entity name if mentioned",
    )
    source_channel: Optional[str] = Field(
        default=None,
        description="Slack channel where the thread originated",
    )
    source_thread_ts: Optional[str] = Field(
        default=None,
        description="Slack thread timestamp for linking back",
    )
    reporter: Optional[str] = Field(
        default=None,
        description="Slack user who initiated the thread",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="LLM confidence in the extraction",
    )
    needs_mapping_review: bool = Field(
        default=False,
        description="True when no deterministic mapping exists for the agency/jurisdiction",
    )
